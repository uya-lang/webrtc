#!/usr/bin/env python3
import os
import re
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
AGENT_DIR = ROOT / ".agent"
TODO_FILE = ROOT / "docs/todo.md"
STATE_FILE = AGENT_DIR / "state.json"
LOG_DIR = AGENT_DIR / "logs"

CODEX_CMD = os.environ.get("CODEX_CMD", "codex")
SLEEP_SECONDS = int(os.environ.get("AGENT_SLEEP", "3"))
MAX_FAILS_PER_TASK = int(os.environ.get("MAX_FAILS_PER_TASK", "3"))

AGENT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_state():
    if not STATE_FILE.exists():
        return {
            "done": [],
            "failed": {},
            "current": None,
            "updated_at": now()
        }

    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state):
    state["updated_at"] = now()
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def parse_todo():
    """
    支持 todo.md 格式：

    - [ ] 修改 parser 错误处理
    - [ ] 增加 runtime 测试
    - [x] 已完成任务
    """

    if not TODO_FILE.exists():
        raise FileNotFoundError("缺少 todo.md")

    tasks = []

    for line in TODO_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*-\s+\[( |x|X)\]\s+(.+)$", line)
        if not m:
            continue

        checked, text = m.groups()
        task_id = str(abs(hash(text)))

        tasks.append({
            "id": task_id,
            "text": text.strip(),
            "done_in_file": checked.lower() == "x"
        })

    return tasks


def mark_done_in_todo(task_text):
    content = TODO_FILE.read_text(encoding="utf-8")
    pattern = r"^(\s*-\s+)\[ \](\s+" + re.escape(task_text) + r"\s*)$"
    content = re.sub(pattern, r"\1[x]\2", content, flags=re.MULTILINE)
    TODO_FILE.write_text(content, encoding="utf-8")


def choose_next_task(tasks, state):
    for task in tasks:
        if task["done_in_file"]:
            continue

        if task["id"] in state["done"]:
            continue

        fails = state["failed"].get(task["id"], 0)
        if fails >= MAX_FAILS_PER_TASK:
            continue

        return task

    return None


def git_commit(message):
    subprocess.run(["git", "add", "."], cwd=ROOT)

    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=ROOT
    )

    if diff.returncode == 0:
        return False

    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=ROOT
    )

    return True


def run_codex(task):
    prompt = f"""
你是一个代码执行 Agent。

当前任务：

{task["text"]}

要求：
1. 只完成这个任务，不要扩大范围。
2. 修改代码后运行相关测试。
3. 如果无法完成，说明原因。
4. 完成后总结修改了哪些文件。
"""

    log_file = LOG_DIR / f"{task['id']}.log"

    cmd = [
        CODEX_CMD,
        "exec",
        "--cd",
        str(ROOT),
        prompt
    ]

    with log_file.open("w", encoding="utf-8") as f:
        f.write(f"[{now()}] START TASK\n")
        f.write(task["text"] + "\n\n")
        f.write("CMD: " + " ".join(cmd[:4]) + " <prompt>\n\n")
        f.flush()

        process = subprocess.run(
            cmd,
            cwd=ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True
        )

        f.write(f"\n[{now()}] EXIT CODE: {process.returncode}\n")

    return process.returncode == 0


def main():
    print("[agent] start")

    while True:
        state = load_state()
        tasks = parse_todo()
        task = choose_next_task(tasks, state)

        if task is None:
            print("[agent] no task left")
            break

        print(f"[agent] run: {task['text']}")

        state["current"] = task
        save_state(state)

        ok = run_codex(task)

        if ok:
            print(f"[agent] done: {task['text']}")

            state["done"].append(task["id"])
            state["current"] = None

            mark_done_in_todo(task["text"])
            save_state(state)

            git_commit(f"agent: {task['text']}")

        else:
            print(f"[agent] failed: {task['text']}")

            state["failed"][task["id"]] = state["failed"].get(task["id"], 0) + 1
            state["current"] = None
            save_state(state)

            git_commit(f"agent failed: {task['text']}")

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()