#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

DEFAULT_TODO_CANDIDATES = (
    "docs/todo.md",
    "todo.md",
    "TODO.md",
)
DEFAULT_GITIGNORE_ENTRIES = (
    ".agent/logs/*",
    ".agent/state*.json",
    "__pycache__/",
)
RESULT_PREFIX = "AGENT_RESULT_JSON:"
TOOLCHAIN_BUG_SECTIONS = (
    "## Summary",
    "## Affected Tasks",
    "## Toolchain Command",
    "## Actual Error",
    "## Expected Behavior",
    "## Repro File",
    "## Repro Code",
    "## Notes",
)

CODEX_CMD = os.environ.get("CODEX_CMD", "codex")
SLEEP_SECONDS = int(os.environ.get("AGENT_SLEEP", "3"))
HEARTBEAT_SECONDS = max(1, int(os.environ.get("AGENT_HEARTBEAT", "15")))
MAX_FAILS_PER_TASK = int(os.environ.get("MAX_FAILS_PER_TASK", "3"))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Codex against a todo file until no runnable task remains.",
    )
    parser.add_argument(
        "todo",
        nargs="?",
        default=None,
        help="Todo file path, relative to the project root by default.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Project root directory. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--todo",
        dest="todo_flag",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show the current agent status for the selected project/todo and exit.",
    )
    parser.add_argument(
        "--status-lines",
        type=int,
        default=20,
        help="How many recent log lines to show with --status. Default: 20.",
    )
    args = parser.parse_args()

    if args.todo and args.todo_flag and args.todo != args.todo_flag:
        parser.error("use either the positional todo path or --todo, not both")

    args.todo = args.todo_flag or args.todo
    return args


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def timestamp_for_filename():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def format_duration(total_seconds):
    total_seconds = max(0, int(total_seconds))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def format_bytes(byte_count):
    byte_count = max(0, int(byte_count))
    units = ("B", "KB", "MB", "GB")
    value = float(byte_count)

    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024.0

    return f"{byte_count}B"


def resolve_root(raw_root):
    cwd = Path.cwd().resolve()
    if raw_root is None:
        return cwd

    path = Path(raw_root).expanduser()
    if not path.is_absolute():
        path = (cwd / path).resolve()
    else:
        path = path.resolve()
    return path


def resolve_path(root, raw_path):
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    else:
        path = path.resolve()
    return path


def path_label(root, path):
    root = root.resolve()
    path = Path(path).resolve()

    if path == root:
        return "."

    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def find_default_todo(root):
    for candidate in DEFAULT_TODO_CANDIDATES:
        todo_file = (root / candidate).resolve()
        if todo_file.exists():
            return todo_file

    return (root / DEFAULT_TODO_CANDIDATES[0]).resolve()


def resolve_todo_file(root, raw_path):
    if raw_path is None:
        return find_default_todo(root)
    return resolve_path(root, raw_path)


def todo_label(root, todo_file):
    return path_label(root, todo_file)


def todo_slug(root, todo_file):
    label = todo_label(root, todo_file).lower()
    safe = re.sub(r"[^a-z0-9]+", "-", label).strip("-") or "todo"
    digest = hashlib.sha1(str(todo_file).encode("utf-8")).hexdigest()[:10]
    return f"{safe[:40]}-{digest}"


def is_primary_todo(root, todo_file):
    primary_candidates = {(root / candidate).resolve() for candidate in DEFAULT_TODO_CANDIDATES}
    return todo_file.resolve() in primary_candidates


def ensure_gitignore(root):
    gitignore_path = root / ".gitignore"

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        existing_lines = content.splitlines()
    else:
        content = ""
        existing_lines = []

    existing_entries = {line.strip() for line in existing_lines if line.strip()}
    missing_entries = [entry for entry in DEFAULT_GITIGNORE_ENTRIES if entry not in existing_entries]

    if not missing_entries:
        return gitignore_path

    new_lines = list(existing_lines)
    if new_lines and new_lines[-1].strip():
        new_lines.append("")
    new_lines.extend(missing_entries)

    gitignore_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return gitignore_path


def build_runtime_paths(root, todo_file):
    agent_dir = root / ".agent"
    state_file = agent_dir / "state.json"
    log_dir = agent_dir / "logs"
    toolchain_bug_dir = agent_dir / "toolchain-bugs"
    toolchain_bug_repro_dir = toolchain_bug_dir / "repros"

    agent_dir.mkdir(exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    toolchain_bug_repro_dir.mkdir(parents=True, exist_ok=True)

    if not is_primary_todo(root, todo_file):
        slug = todo_slug(root, todo_file)
        state_file = agent_dir / f"state-{slug}.json"
        log_dir = log_dir / slug
        log_dir.mkdir(parents=True, exist_ok=True)

    return {
        "root": root,
        "todo_file": todo_file,
        "state_file": state_file,
        "log_dir": log_dir,
        "toolchain_bug_dir": toolchain_bug_dir,
        "toolchain_bug_repro_dir": toolchain_bug_repro_dir,
    }


def empty_state(root, todo_file):
    return {
        "project_root": str(root),
        "todo_file": str(todo_file),
        "done": [],
        "failed": {},
        "toolchain_bugs": [],
        "commits": [],
        "pending_commit": None,
        "current": None,
        "updated_at": now(),
    }


def load_state(state_file, root, todo_file):
    if not state_file.exists():
        return empty_state(root, todo_file)

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return empty_state(root, todo_file)

    if not isinstance(state, dict):
        return empty_state(root, todo_file)

    state.setdefault("done", [])
    state.setdefault("failed", {})
    if "toolchain_bugs" not in state:
        state["toolchain_bugs"] = state.pop("compiler_bugs", [])
    state.setdefault("commits", [])
    state.setdefault("pending_commit", None)
    state.setdefault("current", None)
    state["project_root"] = str(root)
    state["todo_file"] = str(todo_file)

    return state


def save_state(state_file, state):
    state["updated_at"] = now()
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def tail_lines(path, limit):
    if limit <= 0 or not path.exists():
        return []

    return path.read_text(encoding="utf-8").splitlines()[-limit:]


def latest_log_file(log_dir):
    if not log_dir.exists():
        return None

    log_files = sorted(log_dir.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not log_files:
        return None

    return log_files[0]


def print_status(paths, state, status_lines):
    root = paths["root"]
    print(f"[agent] state file: {path_label(root, paths['state_file'])}")
    print(f"[agent] project root: {path_label(root, root)}")
    print(f"[agent] todo: {todo_label(root, resolve_path(root, state['todo_file']))}")
    print(f"[agent] updated at: {state.get('updated_at', '')}")

    current = state.get("current")
    if not current:
        print("[agent] current: idle")
        pending_commit = state.get("pending_commit")
        if isinstance(pending_commit, dict):
            print("[agent] pending commit recovery: yes")
            print(f"[agent] recovery attempts: {pending_commit.get('attempts', 0)}")
            pending_tasks = pending_commit.get("tasks", [])
            if pending_tasks:
                preview_count = min(5, len(pending_tasks))
                print(f"[agent] pending tasks ({preview_count}/{len(pending_tasks)}):")
                for index, task in enumerate(pending_tasks[:preview_count], start=1):
                    print(f"  {index}. {task}")
            pending_reports = pending_commit.get("toolchain_bug_reports", [])
            if pending_reports:
                preview_count = min(5, len(pending_reports))
                print(f"[agent] pending bug reports ({preview_count}/{len(pending_reports)}):")
                for index, report in enumerate(pending_reports[:preview_count], start=1):
                    print(f"  {index}. {report}")
        return

    print("[agent] current: running")
    print(f"[agent] started at: {current.get('started_at', '')}")
    print(f"[agent] task count: {current.get('task_count', 0)}")

    current_task = current.get("current_task") or current.get("text")
    if current_task:
        print(f"[agent] current task: {current_task}")

    pid = current.get("pid")
    if pid:
        print(f"[agent] pid: {pid}")

    elapsed_seconds = current.get("elapsed_seconds")
    if isinstance(elapsed_seconds, int):
        print(f"[agent] elapsed: {format_duration(elapsed_seconds)}")

    heartbeat_at = current.get("heartbeat_at")
    if heartbeat_at:
        print(f"[agent] heartbeat at: {heartbeat_at}")

    log_bytes = current.get("log_bytes")
    if isinstance(log_bytes, int):
        print(f"[agent] log size: {format_bytes(log_bytes)}")

    log_updated_at = current.get("log_updated_at")
    if log_updated_at:
        print(f"[agent] log updated at: {log_updated_at}")

    tasks = current.get("tasks", [])
    if tasks:
        preview_count = min(5, len(tasks))
        print(f"[agent] batch preview ({preview_count}/{len(tasks)}):")
        for index, task in enumerate(tasks[:preview_count], start=1):
            print(f"  {index}. {task}")

    log_path_value = current.get("log_file")
    if isinstance(log_path_value, str) and log_path_value.strip():
        log_path = resolve_path(root, log_path_value.strip())
    else:
        log_path = latest_log_file(paths["log_dir"])
        if log_path is None:
            return

    print(f"[agent] log file: {path_label(root, log_path)}")
    recent_lines = tail_lines(log_path, status_lines)
    if not recent_lines:
        return

    print(f"[agent] recent log lines ({len(recent_lines)}):")
    for line in recent_lines:
        print(line)


def make_task_id(todo_file, task_text, occurrence):
    raw = f"{todo_file.resolve()}::{task_text}::{occurrence}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def parse_todo(todo_file):
    """
    支持 markdown checklist 格式：

    - [ ] 实现功能
    - [x] 已完成功能
    """

    if not todo_file.exists():
        raise FileNotFoundError(f"缺少 todo 文件: {todo_file}")

    tasks = []
    occurrences = {}

    for line_no, line in enumerate(todo_file.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.match(r"^\s*-\s+\[( |x|X)\]\s+(.+)$", line)
        if not match:
            continue

        checked, text = match.groups()
        text = text.strip()
        occurrence = occurrences.get(text, 0) + 1
        occurrences[text] = occurrence

        tasks.append(
            {
                "id": make_task_id(todo_file, text, occurrence),
                "text": text,
                "done_in_file": checked.lower() == "x",
                "line_no": line_no,
            }
        )

    return tasks


def choose_runnable_tasks(tasks, state):
    runnable = []

    for task in tasks:
        if task["done_in_file"]:
            continue

        if task["id"] in state["done"]:
            continue

        fails = state["failed"].get(task["id"], 0)
        if fails >= MAX_FAILS_PER_TASK:
            continue

        runnable.append(task)

    return runnable


def choose_exhausted_tasks(tasks, state):
    exhausted = []

    for task in tasks:
        if task["done_in_file"]:
            continue

        if task["id"] in state["done"]:
            continue

        fails = state["failed"].get(task["id"], 0)
        if fails >= MAX_FAILS_PER_TASK:
            exhausted.append(task)

    return exhausted


def is_git_repo(root):
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return probe.returncode == 0


def summarize_tasks(tasks, limit):
    if not tasks:
        return "无"

    lines = []
    for index, task in enumerate(tasks[:limit], start=1):
        lines.append(f"{index}. {task['text']}")

    if len(tasks) > limit:
        lines.append(f"... 还有 {len(tasks) - limit} 个任务")

    return "\n".join(lines)


def summarize_strings(items, limit):
    if not items:
        return "无"

    lines = []
    for index, item in enumerate(items[:limit], start=1):
        lines.append(f"{index}. {item}")

    if len(items) > limit:
        lines.append(f"... 还有 {len(items) - limit} 项")

    return "\n".join(lines)


def print_batch_preview(tasks, limit=5):
    if not tasks:
        return

    preview_count = min(limit, len(tasks))
    print(f"[agent] batch preview ({preview_count}/{len(tasks)}):")
    for index, task in enumerate(tasks[:preview_count], start=1):
        print(f"[agent]   {index}. {task['text']}")


def build_prompt(root, todo_file, runnable_tasks, exhausted_tasks, toolchain_bug_dir, toolchain_bug_repro_dir):
    todo_path = todo_label(root, todo_file)
    project_root = path_label(root, root)
    runnable_preview = summarize_tasks(runnable_tasks, limit=20)
    exhausted_preview = summarize_tasks(exhausted_tasks, limit=10)
    toolchain_bug_dir_label = path_label(root, toolchain_bug_dir)
    toolchain_bug_repro_dir_label = path_label(root, toolchain_bug_repro_dir)
    git_repo_note = "是" if is_git_repo(root) else "否"

    return f"""
你是一个代码执行 Agent。

这次要处理的项目根目录：
{project_root}

这次要处理的 todo 文件：
{todo_path}

当前目录是否为 git 仓库：
{git_repo_note}

目标：
在一次 Codex 运行里尽量多完成这个 todo 文件中的未勾选任务，而不是只做一个任务。

当前可处理任务数：{len(runnable_tasks)}
当前因失败次数达到上限而跳过的任务数：{len(exhausted_tasks)}

本轮优先关注的前 20 个任务：
{runnable_preview}

本轮先跳过这些达到失败上限的任务：
{exhausted_preview}

要求：
1. 直接读取并更新 `{todo_path}`，把它当作任务真实来源。
2. 一次性尽量完成多个未勾选任务，不要只做一个。
3. 默认按 todo 文件顺序推进；如果某个任务明确阻塞，但后续任务独立且能安全推进，继续处理后面的独立任务。
4. 对代码实现类任务强制执行 TDD：先写或补最小 failing test，再运行它确认失败，然后实现最小改动让它通过，最后做必要的重构和回归。
5. 优先复用项目里已有的测试、构建、lint、benchmark 入口；如果缺少测试基座而某个 todo 明确要求补齐，就先补最小可运行的项目级测试基座再继续。
6. 只有在任务真正完成并且相关验证通过后，才把对应项改成 `[x]`，并且保留原任务文本，不要改写任务描述。
7. 对暂时做不完的任务保持 `[ ]`，并在总结中说明阻塞原因。
8. 修改代码后运行相关测试、构建或最小必要验证，并在输出里说明执行了哪些验证，以及 TDD 的 red/green 分别用了什么命令。
9. 如果怀疑遇到了项目工具链 bug（例如编译器、解释器、构建系统、测试运行器、包管理器本身的问题），必须在继续前把 bug 记录下来：
   - 先把问题缩减成最小可复现代码或最小可复现输入。
   - 把复现文件写到 `{toolchain_bug_repro_dir_label}/` 下，文件名用时间戳加短描述，扩展名按项目实际类型决定。
   - 把 bug 报告写到 `{toolchain_bug_dir_label}/` 下，文件名与 repro 对应，后缀 `.md`。
   - 报告必须包含以下一级小节，标题要完全一致：
     `## Summary`
     `## Affected Tasks`
     `## Toolchain Command`
     `## Actual Error`
     `## Expected Behavior`
     `## Repro File`
     `## Repro Code`
     `## Notes`
   - `## Repro File` 小节下一行只放 repro 文件路径，并用反引号包起来。
   - `## Repro Code` 小节必须包含一个 fenced code block，内容要和 repro 文件内容一致；语言标记可按文件类型填写，也可以留空。
   - 被该工具链 bug 阻塞的 todo 任务必须留在 `[ ]`，并写进 `blocked`。
10. 如果当前目录是 git 仓库，并且你在本轮完成了任务或新增了工具链 bug 记录，你必须在本轮结束前立即自己创建提交；不要依赖外层脚本代为提交，也不要把已勾选但未提交的 todo 留给下一轮。
11. 提交要求：
   - 优先在本轮结束时创建一个清晰、可读的普通提交；只有在工作天然分成两块时才拆成多个提交。
   - 提交消息要自然、简洁，能概括本轮真实改动，不要使用机械化模板。
   - 只 stage 本轮相关文件；如果工作区里有无关脏改动，不要把它们一起提交。
   - 不要 amend 既有提交。
12. 如果项目不是 git 仓库，也继续完成任务，并把 `commits` 留空数组。
13. 不要回退用户已有改动，不要执行 destructive git 操作，也不要扩大到和这个 todo 无关的工作。
14. 结束前必须输出一行严格单行 JSON，格式如下：
{RESULT_PREFIX} {{"completed":["任务1"],"blocked":["任务2"],"deferred":["任务3"],"toolchain_bugs":[".agent/toolchain-bugs/bug-report.md"],"commits":["abc1234"],"summary":"一句话总结"}}

字段说明：
- completed：本次真正完成、并且已经在 todo 文件中勾选的任务文本
- blocked：本次尝试过但暂时无法完成的任务文本
- deferred：本次没有处理或主动留给下次的任务文本
- toolchain_bugs：本次新增或更新的工具链 bug 报告 markdown 路径
- commits：本次新创建的 git commit 哈希，短哈希或长哈希都可以；非 git 项目时用空数组
- 没有内容时使用空数组
"""


def build_commit_recovery_prompt(root, todo_file, pending_commit):
    todo_path = todo_label(root, todo_file)
    project_root = path_label(root, root)
    task_preview = summarize_strings(pending_commit.get("tasks", []), limit=20)
    bug_preview = summarize_strings(pending_commit.get("toolchain_bug_reports", []), limit=20)
    attempt_count = pending_commit.get("attempts", 0)

    return f"""
你是一个代码执行 Agent。

上一个批次已经完成了部分工作，但没有创建 git commit。
这次不要继续做新的 todo 任务；只处理“补提交”收尾。

项目根目录：
{project_root}

todo 文件：
{todo_path}

待补提交的已完成任务：
{task_preview}

待补提交的 toolchain bug 报告：
{bug_preview}

这是第 {attempt_count} 次补提交尝试。

要求：
1. 先检查当前 git 状态和最近提交，确认哪些未提交改动属于上述任务或 bug 报告。
2. 只 stage 与上述任务或 bug 报告直接相关的文件，立即创建一个或多个清晰、自然的普通提交。
3. 不要继续实现新的 todo 任务，不要扩大工作范围，也不要把无关脏改动一起提交。
4. 如果你发现上一个批次把 todo 勾选早了，先把错误勾选恢复成 `[ ]` 或修正相关文件，再把这次修正提交掉。
5. 结束前必须输出一行严格单行 JSON，格式如下：
{RESULT_PREFIX} {{"completed":[],"blocked":[],"deferred":[],"toolchain_bugs":[],"commits":["abc1234"],"summary":"一句话总结"}}

字段说明：
- `completed`：默认使用空数组，除非这次顺手修正了 todo 状态并重新确认完成
- `blocked`：如果因为明确原因暂时无法完成补提交，写原因对应的任务文本
- `deferred`：默认使用空数组
- `toolchain_bugs`：默认使用空数组；只有这次新增或更新了 bug 报告时才填写
- `commits`：这次新创建的 git commit 哈希，短哈希或长哈希都可以
"""


def make_log_file(log_dir, runnable_tasks):
    first_id = runnable_tasks[0]["id"] if runnable_tasks else "empty"
    return log_dir / f"batch-{timestamp_for_filename()}-{first_id[:8]}.log"


def run_codex(
    root,
    todo_file,
    log_dir,
    runnable_tasks,
    exhausted_tasks,
    toolchain_bug_dir,
    toolchain_bug_repro_dir,
    state_file=None,
    state=None,
    log_file=None,
    prompt_override=None,
):
    prompt = prompt_override or build_prompt(
        root,
        todo_file,
        runnable_tasks,
        exhausted_tasks,
        toolchain_bug_dir,
        toolchain_bug_repro_dir,
    )
    if log_file is None:
        log_file = make_log_file(log_dir, runnable_tasks)

    cmd = [
        CODEX_CMD,
        "exec",
        "--cd",
        str(root),
        prompt,
    ]

    with log_file.open("w", encoding="utf-8") as handle:
        handle.write(f"[{now()}] START BATCH\n")
        handle.write(f"PROJECT_ROOT: {path_label(root, root)}\n")
        handle.write(f"TODO: {todo_label(root, todo_file)}\n")
        handle.write(f"RUNNABLE: {len(runnable_tasks)}\n")
        handle.write(f"EXHAUSTED: {len(exhausted_tasks)}\n\n")
        handle.write(f"TOOLCHAIN_BUG_DIR: {path_label(root, toolchain_bug_dir)}\n")
        handle.write(f"TOOLCHAIN_BUG_REPRO_DIR: {path_label(root, toolchain_bug_repro_dir)}\n\n")
        handle.write(summarize_tasks(runnable_tasks, limit=50) + "\n\n")
        handle.write("CMD: " + " ".join(cmd[:4]) + " <prompt>\n\n")
        handle.flush()

        try:
            process = subprocess.Popen(
                cmd,
                cwd=root,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            handle.write(f"[{now()}] ERROR: command not found: {CODEX_CMD}\n")
            return False, log_file

        start_monotonic = time.monotonic()
        next_heartbeat = start_monotonic + HEARTBEAT_SECONDS
        last_reported_size = log_file.stat().st_size if log_file.exists() else 0
        last_log_size = last_reported_size
        last_log_update_monotonic = start_monotonic
        last_log_update_at = now()

        if state is not None and state_file is not None and isinstance(state.get("current"), dict):
            state["current"]["pid"] = process.pid
            state["current"]["heartbeat_at"] = now()
            state["current"]["elapsed_seconds"] = 0
            state["current"]["log_bytes"] = last_log_size
            state["current"]["log_updated_at"] = last_log_update_at
            save_state(state_file, state)

        while True:
            returncode = process.poll()
            current_monotonic = time.monotonic()
            current_log_size = log_file.stat().st_size if log_file.exists() else 0

            if current_log_size > last_log_size:
                last_log_size = current_log_size
                last_log_update_monotonic = current_monotonic
                last_log_update_at = now()

            if returncode is not None:
                elapsed_seconds = int(current_monotonic - start_monotonic)
                if state is not None and state_file is not None and isinstance(state.get("current"), dict):
                    state["current"]["elapsed_seconds"] = elapsed_seconds
                    state["current"]["heartbeat_at"] = now()
                    state["current"]["log_bytes"] = last_log_size
                    state["current"]["log_updated_at"] = last_log_update_at
                    save_state(state_file, state)
                break

            if current_monotonic >= next_heartbeat:
                elapsed_seconds = int(current_monotonic - start_monotonic)
                delta_bytes = max(0, current_log_size - last_reported_size)
                if delta_bytes > 0:
                    log_note = f"+{format_bytes(delta_bytes)} output"
                else:
                    quiet_for = int(current_monotonic - last_log_update_monotonic)
                    log_note = f"no new output for {format_duration(quiet_for)}"

                current_task = runnable_tasks[0]["text"] if runnable_tasks else "无"
                print(
                    "[agent] heartbeat: "
                    f"{format_duration(elapsed_seconds)} running | "
                    f"current={current_task} | "
                    f"log={path_label(root, log_file)} | "
                    f"{log_note}"
                )

                if state is not None and state_file is not None and isinstance(state.get("current"), dict):
                    state["current"]["elapsed_seconds"] = elapsed_seconds
                    state["current"]["heartbeat_at"] = now()
                    state["current"]["log_bytes"] = current_log_size
                    state["current"]["log_updated_at"] = last_log_update_at
                    save_state(state_file, state)

                last_reported_size = current_log_size
                next_heartbeat = current_monotonic + HEARTBEAT_SECONDS

            time.sleep(1)

        handle.write(f"\n[{now()}] EXIT CODE: {returncode}\n")

    return returncode == 0, log_file


def normalize_string_list(value):
    if not isinstance(value, list):
        return []

    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def parse_agent_result(log_file):
    if not log_file.exists():
        return {}

    for line in reversed(log_file.read_text(encoding="utf-8").splitlines()):
        if not line.startswith(RESULT_PREFIX):
            continue

        payload = line[len(RESULT_PREFIX) :].strip()
        try:
            result = json.loads(payload)
        except json.JSONDecodeError:
            return {}

        if not isinstance(result, dict):
            return {}

        normalized = {
            "completed": normalize_string_list(result.get("completed", [])),
            "blocked": normalize_string_list(result.get("blocked", [])),
            "deferred": normalize_string_list(result.get("deferred", [])),
            "toolchain_bugs": normalize_string_list(
                result.get("toolchain_bugs", result.get("compiler_bugs", []))
            ),
            "commits": normalize_string_list(result.get("commits", [])),
        }

        summary = result.get("summary", "")
        normalized["summary"] = summary.strip() if isinstance(summary, str) else ""
        return normalized

    return {}


def is_path_within(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_toolchain_bug_report(root, report_path, toolchain_bug_dir, toolchain_bug_repro_dir):
    if not report_path.exists() or not report_path.is_file():
        return False

    if report_path.suffix.lower() != ".md":
        return False

    if not is_path_within(report_path, toolchain_bug_dir):
        return False

    content = report_path.read_text(encoding="utf-8")

    for section in TOOLCHAIN_BUG_SECTIONS:
        if section not in content:
            return False

    repro_path_match = re.search(r"## Repro File\s+`([^`\n]+)`", content)
    if repro_path_match is None:
        return False

    repro_code_match = re.search(r"## Repro Code\s+```[^\n]*\n(.*?)\n```", content, re.DOTALL)
    if repro_code_match is None:
        return False

    repro_code = repro_code_match.group(1).strip()
    if not repro_code:
        return False

    repro_path = resolve_path(root, repro_path_match.group(1).strip())
    if not repro_path.exists() or not repro_path.is_file():
        return False

    if not is_path_within(repro_path, toolchain_bug_repro_dir):
        return False

    repro_file_code = repro_path.read_text(encoding="utf-8").strip()
    if repro_file_code != repro_code:
        return False

    return True


def collect_valid_toolchain_bug_reports(root, report_paths, toolchain_bug_dir, toolchain_bug_repro_dir):
    valid_reports = []
    seen = set()

    for raw_path in report_paths:
        report_path = resolve_path(root, raw_path)
        if not validate_toolchain_bug_report(
            root,
            report_path,
            toolchain_bug_dir,
            toolchain_bug_repro_dir,
        ):
            continue

        label = path_label(root, report_path)
        if label in seen:
            continue

        valid_reports.append(label)
        seen.add(label)

    return valid_reports


def is_valid_git_commit(root, commit_ref):
    if not is_git_repo(root):
        return False

    probe = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit_ref}^{{commit}}"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return probe.returncode == 0


def collect_valid_commits(root, commit_refs):
    valid_commits = []
    seen = set()

    for commit_ref in commit_refs:
        if not is_valid_git_commit(root, commit_ref):
            continue
        if commit_ref in seen:
            continue

        valid_commits.append(commit_ref)
        seen.add(commit_ref)

    return valid_commits


def git_head_commit(root):
    if not is_git_repo(root):
        return None

    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if probe.returncode != 0:
        return None

    commit_ref = probe.stdout.strip()
    return commit_ref or None


def collect_new_commits(root, before_commit, after_commit=None):
    if not is_git_repo(root):
        return []

    if after_commit is None:
        after_commit = git_head_commit(root)

    if not after_commit or after_commit == before_commit:
        return []

    revision = after_commit if before_commit is None else f"{before_commit}..{after_commit}"
    probe = subprocess.run(
        ["git", "rev-list", "--reverse", revision],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if probe.returncode != 0:
        return []

    commits = []
    seen = set()
    for line in probe.stdout.splitlines():
        commit_ref = line.strip()
        if not commit_ref or commit_ref in seen:
            continue
        commits.append(commit_ref)
        seen.add(commit_ref)

    return commits


def ensure_pending_commit(state):
    pending_commit = state.get("pending_commit")
    if not isinstance(pending_commit, dict):
        pending_commit = {
            "tasks": [],
            "toolchain_bug_reports": [],
            "attempts": 0,
            "updated_at": now(),
        }
        state["pending_commit"] = pending_commit

    pending_commit.setdefault("tasks", [])
    pending_commit.setdefault("toolchain_bug_reports", [])
    pending_commit.setdefault("attempts", 0)
    pending_commit["updated_at"] = now()
    return pending_commit


def queue_pending_commit(state, completed_tasks, toolchain_bug_reports):
    pending_commit = ensure_pending_commit(state)
    merge_unique_strings(pending_commit["tasks"], [task["text"] for task in completed_tasks])
    merge_unique_strings(pending_commit["toolchain_bug_reports"], toolchain_bug_reports)
    pending_commit["updated_at"] = now()
    return pending_commit


def recovery_task_list(pending_commit):
    task_text = "提交上轮未提交改动"
    pending_tasks = pending_commit.get("tasks", [])
    if pending_tasks:
        task_text = f"提交上轮未提交改动：{pending_tasks[0]}"

    return [
        {
            "id": "commit-recovery",
            "text": task_text,
        }
    ]


def run_pending_commit_recovery(paths, state):
    pending_commit = ensure_pending_commit(state)
    pending_commit["attempts"] = pending_commit.get("attempts", 0) + 1
    pending_commit["updated_at"] = now()

    recovery_tasks = recovery_task_list(pending_commit)
    recovery_log_file = make_log_file(paths["log_dir"], recovery_tasks)
    batch_head_before = git_head_commit(paths["root"])
    state["current"] = {
        "project_root": path_label(paths["root"], paths["root"]),
        "todo_file": todo_label(paths["root"], paths["todo_file"]),
        "started_at": now(),
        "task_count": len(pending_commit.get("tasks", [])),
        "current_task": recovery_tasks[0]["text"],
        "tasks": pending_commit.get("tasks", [])[:20] or pending_commit.get("toolchain_bug_reports", [])[:20],
        "toolchain_bug_dir": path_label(paths["root"], paths["toolchain_bug_dir"]),
        "toolchain_bug_repro_dir": path_label(paths["root"], paths["toolchain_bug_repro_dir"]),
        "git_repo": True,
        "log_file": path_label(paths["root"], recovery_log_file),
        "pid": None,
        "heartbeat_at": None,
        "elapsed_seconds": 0,
        "log_bytes": 0,
        "log_updated_at": None,
    }
    save_state(paths["state_file"], state)

    print("[agent] run recovery: missing commit from previous batch")
    print(f"[agent] recovery attempt: {pending_commit['attempts']}")
    print(f"[agent] current task: {recovery_tasks[0]['text']}")
    if pending_commit.get("tasks"):
        print("[agent] recovery targets:")
        for index, task in enumerate(pending_commit["tasks"][:5], start=1):
            print(f"[agent]   {index}. {task}")

    ok, log_file = run_codex(
        paths["root"],
        paths["todo_file"],
        paths["log_dir"],
        recovery_tasks,
        [],
        paths["toolchain_bug_dir"],
        paths["toolchain_bug_repro_dir"],
        state_file=paths["state_file"],
        state=state,
        log_file=recovery_log_file,
        prompt_override=build_commit_recovery_prompt(paths["root"], paths["todo_file"], pending_commit),
    )

    result = parse_agent_result(log_file)
    reported_commits = collect_valid_commits(paths["root"], result.get("commits", []))
    detected_commits = collect_new_commits(paths["root"], batch_head_before)
    commits = list(reported_commits)
    merge_unique_strings(commits, detected_commits)
    invalid_commits = len(result.get("commits", [])) - len(reported_commits)

    if commits:
        print(f"[agent] recovery committed: {len(commits)}")
        merge_unique_strings(state.setdefault("commits", []), commits)
        state["pending_commit"] = None
        state["current"] = None
        save_state(paths["state_file"], state)
        return True

    if invalid_commits > 0:
        print(f"[agent] recovery ignored invalid commits: {invalid_commits}")

    if not ok:
        print("[agent] recovery batch failed without producing a commit; will retry")
    else:
        print("[agent] recovery batch ended without producing a commit; will retry")

    state["current"] = None
    save_state(paths["state_file"], state)
    return False


def completed_tasks(before_tasks, after_tasks):
    after_by_id = {task["id"]: task for task in after_tasks}
    completed = []

    for task in before_tasks:
        after = after_by_id.get(task["id"])
        if after and not task["done_in_file"] and after["done_in_file"]:
            completed.append(after)

    return completed


def match_tasks_by_text(task_texts, tasks):
    tasks_by_text = {}
    for task in tasks:
        tasks_by_text.setdefault(task["text"], []).append(task)

    matched = []
    matched_ids = set()

    for text in task_texts:
        for task in tasks_by_text.get(text, []):
            if task["id"] in matched_ids:
                continue
            matched.append(task)
            matched_ids.add(task["id"])
            break

    return matched


def exclude_tasks(tasks, excluded_tasks):
    excluded_ids = {task["id"] for task in excluded_tasks}
    return [task for task in tasks if task["id"] not in excluded_ids]


def merge_unique_strings(existing_values, new_values):
    known = set(existing_values)

    for value in new_values:
        if value in known:
            continue
        existing_values.append(value)
        known.add(value)


def merge_done_ids(state, tasks):
    done = list(state.get("done", []))
    known = set(done)

    for task in tasks:
        if task["id"] in known:
            continue
        done.append(task["id"])
        known.add(task["id"])
        state["failed"].pop(task["id"], None)

    state["done"] = done


def bump_failures(state, tasks):
    failed = state.setdefault("failed", {})

    for task in tasks:
        failed[task["id"]] = failed.get(task["id"], 0) + 1


def main():
    args = parse_args()
    root = resolve_root(args.root)
    ensure_gitignore(root)
    todo_file = resolve_todo_file(root, args.todo)
    paths = build_runtime_paths(root, todo_file)

    if args.status:
        state = load_state(paths["state_file"], paths["root"], paths["todo_file"])
        print_status(paths, state, args.status_lines)
        return 0

    print(f"[agent] start: root={path_label(root, root)} todo={todo_label(root, todo_file)}")
    git_repo = is_git_repo(paths["root"])

    while True:
        state = load_state(paths["state_file"], paths["root"], paths["todo_file"])

        if git_repo and isinstance(state.get("pending_commit"), dict):
            recovered = run_pending_commit_recovery(paths, state)
            if recovered:
                continue

            time.sleep(SLEEP_SECONDS)
            continue

        tasks_before = parse_todo(paths["todo_file"])
        runnable_tasks = choose_runnable_tasks(tasks_before, state)
        exhausted_tasks = choose_exhausted_tasks(tasks_before, state)

        if not runnable_tasks:
            if exhausted_tasks:
                print(f"[agent] no runnable task left ({len(exhausted_tasks)} blocked by fail limit)")
            else:
                print("[agent] no task left")
            break

        batch_log_file = make_log_file(paths["log_dir"], runnable_tasks)
        batch_head_before = git_head_commit(paths["root"])
        state["current"] = {
            "project_root": path_label(paths["root"], paths["root"]),
            "todo_file": todo_label(paths["root"], paths["todo_file"]),
            "started_at": now(),
            "task_count": len(runnable_tasks),
            "current_task": runnable_tasks[0]["text"],
            "tasks": [task["text"] for task in runnable_tasks[:20]],
            "toolchain_bug_dir": path_label(paths["root"], paths["toolchain_bug_dir"]),
            "toolchain_bug_repro_dir": path_label(paths["root"], paths["toolchain_bug_repro_dir"]),
            "git_repo": git_repo,
            "log_file": path_label(paths["root"], batch_log_file),
            "pid": None,
            "heartbeat_at": None,
            "elapsed_seconds": 0,
            "log_bytes": 0,
            "log_updated_at": None,
        }
        save_state(paths["state_file"], state)

        print(f"[agent] run batch: {len(runnable_tasks)} runnable tasks")
        print(f"[agent] current task: {runnable_tasks[0]['text']}")
        print_batch_preview(runnable_tasks)
        ok, log_file = run_codex(
            paths["root"],
            paths["todo_file"],
            paths["log_dir"],
            runnable_tasks,
            exhausted_tasks,
            paths["toolchain_bug_dir"],
            paths["toolchain_bug_repro_dir"],
            state_file=paths["state_file"],
            state=state,
            log_file=batch_log_file,
        )

        tasks_after = parse_todo(paths["todo_file"])
        result = parse_agent_result(log_file)
        newly_completed = completed_tasks(tasks_before, tasks_after)
        blocked_tasks = match_tasks_by_text(result.get("blocked", []), runnable_tasks)
        blocked_tasks = exclude_tasks(blocked_tasks, newly_completed)
        toolchain_bug_reports = collect_valid_toolchain_bug_reports(
            paths["root"],
            result.get("toolchain_bugs", []),
            paths["toolchain_bug_dir"],
            paths["toolchain_bug_repro_dir"],
        )
        invalid_toolchain_bug_reports = len(result.get("toolchain_bugs", [])) - len(toolchain_bug_reports)
        reported_commits = collect_valid_commits(paths["root"], result.get("commits", []))
        detected_commits = collect_new_commits(paths["root"], batch_head_before)
        commits = list(reported_commits)
        merge_unique_strings(commits, detected_commits)
        invalid_commits = len(result.get("commits", [])) - len(reported_commits)
        commit_required = git_repo and (bool(newly_completed) or bool(toolchain_bug_reports))

        if commit_required and not commits:
            reasons = []
            if newly_completed:
                reasons.append(f"{len(newly_completed)} completed task(s)")
            if toolchain_bug_reports:
                reasons.append(f"{len(toolchain_bug_reports)} toolchain bug report(s)")
            joined_reasons = " and ".join(reasons)
            print(f"[agent] warning: batch produced {joined_reasons} but no new git commit was created")
            print("[agent] queue recovery: agent will run a commit-only follow-up batch")
            queue_pending_commit(state, newly_completed, toolchain_bug_reports)
            state["current"] = None
            save_state(paths["state_file"], state)
            continue

        if newly_completed:
            print(f"[agent] completed: {len(newly_completed)} task(s)")
            merge_done_ids(state, newly_completed)

        if blocked_tasks:
            print(f"[agent] blocked: {len(blocked_tasks)} task(s)")
            bump_failures(state, blocked_tasks)

        if toolchain_bug_reports:
            print(f"[agent] recorded toolchain bug reports: {len(toolchain_bug_reports)}")
            merge_unique_strings(state.setdefault("toolchain_bugs", []), toolchain_bug_reports)

        if invalid_toolchain_bug_reports > 0:
            print(f"[agent] ignored invalid toolchain bug reports: {invalid_toolchain_bug_reports}")

        if commits:
            print(f"[agent] recorded commits: {len(commits)}")
            merge_unique_strings(state.setdefault("commits", []), commits)

        if invalid_commits > 0:
            print(f"[agent] ignored invalid commits: {invalid_commits}")

        if not newly_completed and not blocked_tasks and not ok:
            first_task = runnable_tasks[0]
            print(f"[agent] failed without progress: {first_task['text']}")
            bump_failures(state, [first_task])

        if not newly_completed and not blocked_tasks and ok:
            first_task = runnable_tasks[0]
            print(f"[agent] no explicit progress reported, mark failed once: {first_task['text']}")
            bump_failures(state, [first_task])

        state["current"] = None
        save_state(paths["state_file"], state)

        time.sleep(SLEEP_SECONDS)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
