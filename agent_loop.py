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

ROOT = Path(__file__).resolve().parent
AGENT_DIR = ROOT / ".agent"
DEFAULT_TODO_FILE = ROOT / "docs/todo.md"
DEFAULT_STATE_FILE = AGENT_DIR / "state.json"
DEFAULT_LOG_DIR = AGENT_DIR / "logs"
RESULT_PREFIX = "AGENT_RESULT_JSON:"

CODEX_CMD = os.environ.get("CODEX_CMD", "codex")
SLEEP_SECONDS = int(os.environ.get("AGENT_SLEEP", "3"))
MAX_FAILS_PER_TASK = int(os.environ.get("MAX_FAILS_PER_TASK", "3"))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Codex against a todo file until no runnable task remains.",
    )
    parser.add_argument(
        "--todo",
        default=str(DEFAULT_TODO_FILE.relative_to(ROOT)),
        help="Todo file path, relative to the repo root by default.",
    )
    return parser.parse_args()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def timestamp_for_filename():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def resolve_todo_file(raw_path):
    todo_file = Path(raw_path).expanduser()
    if not todo_file.is_absolute():
        todo_file = (ROOT / todo_file).resolve()
    else:
        todo_file = todo_file.resolve()
    return todo_file


def todo_label(todo_file):
    try:
        return todo_file.relative_to(ROOT).as_posix()
    except ValueError:
        return str(todo_file)


def todo_slug(todo_file):
    label = todo_label(todo_file).lower()
    safe = re.sub(r"[^a-z0-9]+", "-", label).strip("-") or "todo"
    digest = hashlib.sha1(str(todo_file).encode("utf-8")).hexdigest()[:10]
    return f"{safe[:40]}-{digest}"


def build_runtime_paths(todo_file):
    AGENT_DIR.mkdir(exist_ok=True)

    if todo_file == DEFAULT_TODO_FILE.resolve():
        state_file = DEFAULT_STATE_FILE
        log_dir = DEFAULT_LOG_DIR
    else:
        slug = todo_slug(todo_file)
        state_file = AGENT_DIR / f"state-{slug}.json"
        log_dir = DEFAULT_LOG_DIR / slug

    log_dir.mkdir(parents=True, exist_ok=True)

    return {
        "todo_file": todo_file,
        "state_file": state_file,
        "log_dir": log_dir,
    }


def empty_state(todo_file):
    return {
        "todo_file": str(todo_file),
        "done": [],
        "failed": {},
        "current": None,
        "updated_at": now(),
    }


def load_state(state_file, todo_file):
    if not state_file.exists():
        return empty_state(todo_file)

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return empty_state(todo_file)

    if not isinstance(state, dict):
        return empty_state(todo_file)

    state.setdefault("done", [])
    state.setdefault("failed", {})
    state.setdefault("current", None)
    state["todo_file"] = str(todo_file)

    return state


def save_state(state_file, state):
    state["updated_at"] = now()
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def make_task_id(todo_file, task_text, occurrence):
    raw = f"{todo_file.resolve()}::{task_text}::{occurrence}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def parse_todo(todo_file):
    """
    支持 todo.md 格式：

    - [ ] 修改 parser 错误处理
    - [ ] 增加 runtime 测试
    - [x] 已完成任务
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


def git_commit(message):
    subprocess.run(["git", "add", "."], cwd=ROOT)

    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=ROOT,
    )

    if diff.returncode == 0:
        return False

    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=ROOT,
    )

    return True


def summarize_tasks(tasks, limit):
    if not tasks:
        return "无"

    lines = []
    for index, task in enumerate(tasks[:limit], start=1):
        lines.append(f"{index}. {task['text']}")

    if len(tasks) > limit:
        lines.append(f"... 还有 {len(tasks) - limit} 个任务")

    return "\n".join(lines)


def build_prompt(todo_file, runnable_tasks, exhausted_tasks):
    todo_path = todo_label(todo_file)
    runnable_preview = summarize_tasks(runnable_tasks, limit=20)
    exhausted_preview = summarize_tasks(exhausted_tasks, limit=10)

    return f"""
你是一个代码执行 Agent。

这次要处理的 todo 文件：
{todo_path}

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
4. 只有在任务真正完成并且相关验证通过后，才把对应项改成 `[x]`，并且保留原任务文本，不要改写任务描述。
5. 对暂时做不完的任务保持 `[ ]`，并在总结中说明阻塞原因。
6. 修改代码后运行相关测试、构建或最小必要验证，并在输出里说明执行了哪些验证。
7. 不要回退用户已有改动，不要执行 destructive git 操作，也不要扩大到和这个 todo 无关的工作。
8. 结束前必须输出一行严格单行 JSON，格式如下：
{RESULT_PREFIX} {{"completed":["任务1"],"blocked":["任务2"],"deferred":["任务3"],"summary":"一句话总结"}}

字段说明：
- completed：本次真正完成、并且已经在 todo 文件中勾选的任务文本
- blocked：本次尝试过但暂时无法完成的任务文本
- deferred：本次没有处理或主动留给下次的任务文本
- 没有内容时使用空数组
"""


def make_log_file(log_dir, runnable_tasks):
    first_id = runnable_tasks[0]["id"] if runnable_tasks else "empty"
    return log_dir / f"batch-{timestamp_for_filename()}-{first_id[:8]}.log"


def run_codex(todo_file, log_dir, runnable_tasks, exhausted_tasks):
    prompt = build_prompt(todo_file, runnable_tasks, exhausted_tasks)
    log_file = make_log_file(log_dir, runnable_tasks)

    cmd = [
        CODEX_CMD,
        "exec",
        "--cd",
        str(ROOT),
        prompt,
    ]

    with log_file.open("w", encoding="utf-8") as handle:
        handle.write(f"[{now()}] START BATCH\n")
        handle.write(f"TODO: {todo_label(todo_file)}\n")
        handle.write(f"RUNNABLE: {len(runnable_tasks)}\n")
        handle.write(f"EXHAUSTED: {len(exhausted_tasks)}\n\n")
        handle.write(summarize_tasks(runnable_tasks, limit=50) + "\n\n")
        handle.write("CMD: " + " ".join(cmd[:4]) + " <prompt>\n\n")
        handle.flush()

        try:
            process = subprocess.run(
                cmd,
                cwd=ROOT,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            handle.write(f"[{now()}] ERROR: command not found: {CODEX_CMD}\n")
            return False, log_file

        handle.write(f"\n[{now()}] EXIT CODE: {process.returncode}\n")

    return process.returncode == 0, log_file


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

        normalized = {}
        for key in ("completed", "blocked", "deferred"):
            value = result.get(key, [])
            if isinstance(value, list):
                normalized[key] = [item.strip() for item in value if isinstance(item, str) and item.strip()]
            else:
                normalized[key] = []

        summary = result.get("summary", "")
        normalized["summary"] = summary.strip() if isinstance(summary, str) else ""
        return normalized

    return {}


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


def build_commit_message(todo_file, newly_completed, blocked_tasks, progress_made):
    label = todo_label(todo_file)

    if newly_completed:
        if len(newly_completed) == 1:
            return f"agent: {newly_completed[0]['text']}"
        return f"agent: completed {len(newly_completed)} tasks from {label}"

    if blocked_tasks:
        if len(blocked_tasks) == 1:
            return f"agent blocked: {blocked_tasks[0]['text']}"
        return f"agent blocked: {len(blocked_tasks)} tasks from {label}"

    if progress_made:
        return f"agent: updated {label}"

    return f"agent failed: no progress in {label}"


def main():
    args = parse_args()
    todo_file = resolve_todo_file(args.todo)
    paths = build_runtime_paths(todo_file)

    print(f"[agent] start: todo={todo_label(todo_file)}")

    while True:
        state = load_state(paths["state_file"], paths["todo_file"])
        tasks_before = parse_todo(paths["todo_file"])
        runnable_tasks = choose_runnable_tasks(tasks_before, state)
        exhausted_tasks = choose_exhausted_tasks(tasks_before, state)

        if not runnable_tasks:
            if exhausted_tasks:
                print(f"[agent] no runnable task left ({len(exhausted_tasks)} blocked by fail limit)")
            else:
                print("[agent] no task left")
            break

        state["current"] = {
            "todo_file": str(paths["todo_file"]),
            "task_count": len(runnable_tasks),
            "tasks": [task["text"] for task in runnable_tasks[:20]],
        }
        save_state(paths["state_file"], state)

        print(f"[agent] run batch: {len(runnable_tasks)} runnable tasks")
        ok, log_file = run_codex(
            paths["todo_file"],
            paths["log_dir"],
            runnable_tasks,
            exhausted_tasks,
        )

        tasks_after = parse_todo(paths["todo_file"])
        result = parse_agent_result(log_file)
        newly_completed = completed_tasks(tasks_before, tasks_after)
        blocked_tasks = match_tasks_by_text(result.get("blocked", []), runnable_tasks)
        blocked_tasks = exclude_tasks(blocked_tasks, newly_completed)

        if newly_completed:
            print(f"[agent] completed: {len(newly_completed)} task(s)")
            merge_done_ids(state, newly_completed)

        if blocked_tasks:
            print(f"[agent] blocked: {len(blocked_tasks)} task(s)")
            bump_failures(state, blocked_tasks)

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

        progress_made = bool(newly_completed)
        git_commit(build_commit_message(paths["todo_file"], newly_completed, blocked_tasks, progress_made))

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
