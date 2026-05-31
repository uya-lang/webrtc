#!/usr/bin/env python3
import argparse
import codecs
import hashlib
import json
import os
import re
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import time
import unicodedata
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
# agent_loop expects child codex runs to be able to stage and commit work.
DEFAULT_CODEX_SANDBOX = "danger-full-access"
CODEX_SANDBOX = os.environ.get("CODEX_SANDBOX", DEFAULT_CODEX_SANDBOX).strip()
VALID_CODEX_SANDBOXES = {
    "read-only",
    "workspace-write",
    "danger-full-access",
}


def parse_positive_int_env(name, default):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    try:
        return max(1, int(raw_value.strip() or str(default)))
    except ValueError:
        return default


SLEEP_SECONDS = int(os.environ.get("AGENT_SLEEP", "3"))
HEARTBEAT_SECONDS = max(1, int(os.environ.get("AGENT_HEARTBEAT", "15")))
MAX_FAILS_PER_TASK = int(os.environ.get("MAX_FAILS_PER_TASK", "3"))
MAX_RUNNABLE_TASKS = parse_positive_int_env("MAX_RUNNABLE_TASKS", 20)
RESULT_EXIT_GRACE_SECONDS = max(1, int(os.environ.get("AGENT_RESULT_EXIT_GRACE", "5")))
RESULT_KILL_GRACE_SECONDS = max(1, int(os.environ.get("AGENT_RESULT_KILL_GRACE", "3")))
ANSI_GREEN = "\x1b[32m"
ANSI_RESET = "\x1b[0m"

if not CODEX_SANDBOX:
    CODEX_SANDBOX = DEFAULT_CODEX_SANDBOX

if CODEX_SANDBOX not in VALID_CODEX_SANDBOXES:
    raise SystemExit(
        "unsupported CODEX_SANDBOX={!r}; expected one of: {}".format(
            CODEX_SANDBOX,
            ", ".join(sorted(VALID_CODEX_SANDBOXES)),
        )
    )


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
        "--kill",
        action="store_true",
        help="Stop the running agent_loop.py process and its current child codex run, if any.",
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

    if args.status and args.kill:
        parser.error("use either --status or --kill, not both")

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


def supports_live_output(stream):
    term = os.environ.get("TERM", "").strip().lower()
    is_tty = callable(getattr(stream, "isatty", None)) and stream.isatty()
    return bool(is_tty and term and term != "dumb")


def parse_non_negative_int_env(name):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return None

    try:
        return max(0, int(raw_value.strip() or "0"))
    except ValueError:
        return 0


def detect_live_header_top_padding():
    configured = parse_non_negative_int_env("AGENT_LIVE_HEADER_TOP_PADDING")
    if configured is not None:
        return configured

    term_program = os.environ.get("TERM_PROGRAM", "").strip().lower()
    if term_program == "vscode":
        return 1

    if os.environ.get("VSCODE_INJECTION") or os.environ.get("VSCODE_SHELL_INTEGRATION"):
        return 1

    return 0


def detect_live_footer_bottom_padding():
    configured = parse_non_negative_int_env("AGENT_LIVE_FOOTER_BOTTOM_PADDING")
    if configured is not None:
        return configured

    term_program = os.environ.get("TERM_PROGRAM", "").strip().lower()
    if term_program == "vscode":
        return 1

    if os.environ.get("VSCODE_INJECTION") or os.environ.get("VSCODE_SHELL_INTEGRATION"):
        return 1

    return 0


def clip_display_text(text, width):
    clean = " ".join(str(text).splitlines())
    if width <= 0:
        return ""
    if display_text_width(clean) <= width:
        return clean
    if width <= 3:
        return trim_display_text(clean, width)
    return trim_display_text(clean, width - 3) + "..."


def char_display_width(char):
    if not char:
        return 0
    if char in "\n\r":
        return 0
    if unicodedata.combining(char):
        return 0
    category = unicodedata.category(char)
    if category in {"Cf", "Mn", "Me"}:
        return 0
    if unicodedata.east_asian_width(char) in {"W", "F"}:
        return 2
    return 1


def display_text_width(text):
    return sum(char_display_width(char) for char in str(text))


def trim_display_text(text, width):
    if width <= 0:
        return ""

    trimmed = []
    used = 0
    for char in str(text):
        char_width = char_display_width(char)
        if used + char_width > width:
            break
        trimmed.append(char)
        used += char_width

    return "".join(trimmed)


def pad_display_text(text, width):
    padding = max(0, width - display_text_width(text))
    return str(text) + (" " * padding)


def sanitize_live_output_chunk(text, pending_escape=""):
    data = (pending_escape or "") + text
    if not data:
        return "", ""

    cleaned = []
    index = 0

    while index < len(data):
        char = data[index]

        if char == "\x1b":
            next_index = index + 1
            if next_index >= len(data):
                return "".join(cleaned), data[index:]

            marker = data[next_index]

            if marker == "[":
                cursor = next_index + 1
                while cursor < len(data):
                    if "@" <= data[cursor] <= "~":
                        index = cursor + 1
                        break
                    cursor += 1
                else:
                    return "".join(cleaned), data[index:]
                continue

            if marker == "]":
                cursor = next_index + 1
                while cursor < len(data):
                    current = data[cursor]
                    if current == "\x07":
                        index = cursor + 1
                        break
                    if current == "\x1b":
                        if cursor + 1 >= len(data):
                            return "".join(cleaned), data[index:]
                        if data[cursor + 1] == "\\":
                            index = cursor + 2
                            break
                    cursor += 1
                else:
                    return "".join(cleaned), data[index:]
                continue

            if marker in "PX^_":
                cursor = next_index + 1
                while cursor < len(data):
                    if data[cursor] == "\x1b":
                        if cursor + 1 >= len(data):
                            return "".join(cleaned), data[index:]
                        if data[cursor + 1] == "\\":
                            index = cursor + 2
                            break
                    cursor += 1
                else:
                    return "".join(cleaned), data[index:]
                continue

            index = next_index + 1
            continue

        codepoint = ord(char)
        if char in "\n\r\t" or (32 <= codepoint < 127) or codepoint >= 160:
            cleaned.append(char)
        index += 1

    return "".join(cleaned), ""


def build_live_status_parts(current_task, elapsed_seconds=None, log_path=None, log_note=None):
    task_text = current_task or "无"
    prefix = "[agent] 当前任务: "
    suffix_parts = []

    if isinstance(elapsed_seconds, int):
        suffix_parts.append(f"已运行 {format_duration(elapsed_seconds)}")

    if log_path:
        suffix_parts.append(f"日志 {log_path}")

    if log_note:
        suffix_parts.append(log_note)

    suffix = ""
    if suffix_parts:
        suffix = " | " + " | ".join(suffix_parts)

    return prefix, task_text, suffix


def build_live_meta_parts(elapsed_seconds=None, log_path=None, log_note=None):
    parts = []

    if isinstance(elapsed_seconds, int):
        parts.append(f"已运行 {format_duration(elapsed_seconds)}")

    if log_path:
        parts.append(f"日志 {log_path}")

    if log_note:
        parts.append(log_note)

    return parts


def build_live_status_line(current_task, elapsed_seconds=None, log_path=None, log_note=None):
    prefix, task_text, suffix = build_live_status_parts(
        current_task,
        elapsed_seconds=elapsed_seconds,
        log_path=log_path,
        log_note=log_note,
    )
    return prefix + task_text + suffix


def render_live_status_line(current_task, elapsed_seconds=None, log_path=None, log_note=None, width=None, color=False):
    prefix, task_text, suffix = build_live_status_parts(
        current_task,
        elapsed_seconds=elapsed_seconds,
        log_path=log_path,
        log_note=log_note,
    )

    clipped_task = task_text
    clipped_suffix = suffix

    if isinstance(width, int) and width > 0:
        available = max(0, width - display_text_width(prefix))
        if display_text_width(task_text) + display_text_width(suffix) > available:
            if display_text_width(task_text) >= available:
                clipped_task = clip_display_text(task_text, available)
                clipped_suffix = ""
            else:
                clipped_suffix = clip_display_text(
                    suffix,
                    available - display_text_width(task_text),
                )

    if color and clipped_task:
        colored_task = f"{ANSI_GREEN}{clipped_task}{ANSI_RESET}"
    else:
        colored_task = clipped_task

    return prefix + colored_task + clipped_suffix


def render_live_header_lines(current_task, elapsed_seconds=None, log_path=None, log_note=None, width=None, color=False):
    task_prefix = "[agent] 当前任务: "
    task_text = current_task or "无"
    header_width = max(20, int(width or 80))
    inner_width = max(1, header_width - 4)
    task_prefix_width = display_text_width(task_prefix)
    if task_prefix_width >= inner_width:
        plain_task_content = clip_display_text(task_prefix + task_text, inner_width)
        rendered_task_content = plain_task_content
    else:
        task_available = max(0, inner_width - task_prefix_width)
        task_text = clip_display_text(task_text, task_available)
        plain_task_content = task_prefix + task_text
        if color and task_text:
            rendered_task_content = task_prefix + ANSI_GREEN + task_text + ANSI_RESET
        else:
            rendered_task_content = plain_task_content

    meta_prefix = "[agent] "
    meta_parts = build_live_meta_parts(
        elapsed_seconds=elapsed_seconds,
        log_path=log_path,
        log_note=log_note,
    )
    meta_text = " | ".join(meta_parts) if meta_parts else "等待输出"
    meta_prefix_width = display_text_width(meta_prefix)
    if meta_prefix_width >= inner_width:
        plain_meta_content = clip_display_text(meta_prefix + meta_text, inner_width)
    else:
        meta_available = max(0, inner_width - meta_prefix_width)
        meta_text = clip_display_text(meta_text, meta_available)
        plain_meta_content = meta_prefix + meta_text

    border_line = "+" + ("-" * (header_width - 2)) + "+"
    task_line = "| " + rendered_task_content + (" " * max(0, inner_width - display_text_width(plain_task_content))) + " |"
    meta_line = "| " + pad_display_text(plain_meta_content, inner_width) + " |"

    return border_line, task_line, meta_line, border_line


class LiveOutputDisplay:
    def __init__(self, stream, enabled=None):
        self.stream = stream
        self.enabled = supports_live_output(stream) if enabled is None else enabled
        self.active = False
        self.rows = 24
        self.scroll_bottom = 24
        self.cols = 80
        self.current_task = "无"
        self.last_header = None
        self.pending_escape = ""
        self.header_rows = 4
        self.header_top = 1 + (detect_live_header_top_padding() if self.enabled else 0)
        self.footer_bottom_padding = detect_live_footer_bottom_padding() if self.enabled else 0
        self.task_row = self.header_top + 1
        self.meta_row = self.header_top + 2
        self.border_bottom_row = self.header_top + 3
        self.scroll_top = self.header_top + self.header_rows
        self.cursor_row = self.scroll_top
        self.cursor_col = 1

    def _write(self, text):
        self.stream.write(text)

    def _flush(self):
        flush = getattr(self.stream, "flush", None)
        if callable(flush):
            flush()

    def _refresh_size(self):
        size = shutil.get_terminal_size(fallback=(80, 24))
        cols = max(20, int(size.columns or 80))
        rows = max(self.scroll_top, int(size.lines or 24))
        max_bottom_padding = max(0, rows - self.scroll_top)
        footer_bottom_padding = min(self.footer_bottom_padding, max_bottom_padding)
        scroll_bottom = max(self.scroll_top, rows - footer_bottom_padding)
        size_changed = cols != self.cols or rows != self.rows or scroll_bottom != self.scroll_bottom
        self.cols = cols
        self.rows = rows
        self.scroll_bottom = scroll_bottom
        return size_changed

    def _apply_scroll_region(self):
        self._write(f"\x1b[{self.scroll_top};{self.scroll_bottom}r")
        for row in range(self.scroll_bottom + 1, self.rows + 1):
            self._write(f"\x1b[{row};1H")
            self._write("\x1b[2K")

    def _clamp_cursor(self):
        self.cursor_row = min(max(self.scroll_top, self.cursor_row), self.scroll_bottom)
        self.cursor_col = min(max(1, self.cursor_col), self.cols)

    def _track_cursor(self, text):
        for char in text:
            if char == "\n":
                self.cursor_row = min(self.scroll_bottom, self.cursor_row + 1)
                self.cursor_col = 1
                continue
            if char == "\r":
                self.cursor_col = 1
                continue
            if char == "\t":
                next_stop = ((self.cursor_col - 1) // 8 + 1) * 8 + 1
                self.cursor_col = min(max(1, next_stop), self.cols)
                continue

            char_width = max(0, min(self.cols, char_display_width(char)))
            if char_width == 0:
                continue

            current_offset = self.cursor_col - 1
            if current_offset + char_width > self.cols:
                if self.cursor_row < self.scroll_bottom:
                    self.cursor_row += 1
                current_offset = 0

            if current_offset + char_width >= self.cols:
                if self.cursor_row < self.scroll_bottom:
                    self.cursor_row += 1
                    self.cursor_col = 1
                else:
                    self.cursor_col = self.cols
            else:
                self.cursor_col = current_offset + char_width + 1

        self._clamp_cursor()

    def _draw_header(self, elapsed_seconds=None, log_path=None, log_note=None, force=False):
        if not self.enabled:
            return

        size_changed = self._refresh_size()
        plain_header = render_live_header_lines(
            self.current_task,
            elapsed_seconds=elapsed_seconds,
            log_path=log_path,
            log_note=log_note,
            width=self.cols,
            color=False,
        )
        if plain_header == self.last_header and not force and not size_changed:
            return

        rendered_border_top, rendered_task, rendered_meta, rendered_border_bottom = render_live_header_lines(
            self.current_task,
            elapsed_seconds=elapsed_seconds,
            log_path=log_path,
            log_note=log_note,
            width=self.cols,
            color=True,
        )

        self._clamp_cursor()
        self._apply_scroll_region()
        self._write(f"\x1b[{self.header_top};1H")
        self._write("\x1b[2K")
        self._write(rendered_border_top)
        self._write(f"\x1b[{self.task_row};1H")
        self._write("\x1b[2K")
        self._write(rendered_task)
        self._write(f"\x1b[{self.meta_row};1H")
        self._write("\x1b[2K")
        self._write(rendered_meta)
        self._write(f"\x1b[{self.border_bottom_row};1H")
        self._write("\x1b[2K")
        self._write(rendered_border_bottom)
        self._write(f"\x1b[{self.cursor_row};{self.cursor_col}H")
        self._flush()
        self.last_header = plain_header

    def start(self, current_task):
        self.current_task = current_task or "无"
        self.active = True
        self.last_header = None
        self.pending_escape = ""
        self.cursor_row = self.scroll_top
        self.cursor_col = 1

        if not self.enabled:
            self._write(build_live_status_line(self.current_task) + "\n")
            self._flush()
            return

        self._refresh_size()
        self._write("\x1b[2J\x1b[H")
        self._apply_scroll_region()
        self._write(f"\x1b[{self.scroll_top};1H")
        self._draw_header(force=True)

    def update(self, current_task=None, elapsed_seconds=None, log_path=None, log_note=None, force=False):
        if current_task is not None:
            self.current_task = current_task or "无"

        plain_header = render_live_status_line(
            self.current_task,
            elapsed_seconds=elapsed_seconds,
            log_path=log_path,
            log_note=log_note,
            width=self.cols if self.enabled else None,
            color=False,
        )

        if not self.enabled:
            self.last_header = plain_header
            return

        self._draw_header(
            elapsed_seconds=elapsed_seconds,
            log_path=log_path,
            log_note=log_note,
            force=force,
        )

    def write(self, text):
        if not text:
            return

        if self.enabled:
            text, self.pending_escape = sanitize_live_output_chunk(
                text,
                pending_escape=self.pending_escape,
            )
            if not text:
                return

        self._write(text)
        if self.enabled:
            self._track_cursor(text)
        self._flush()

    def finish(self):
        if not self.active:
            return

        if self.enabled:
            self.pending_escape = ""
            self._write("\x1b[r")
            self._write(f"\x1b[{self.rows};1H")
            self._write("\n")

        self._flush()
        self.active = False


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
        "runner": None,
        "done": [],
        "failed": {},
        "toolchain_bugs": [],
        "commits": [],
        "pending_commit": None,
        "current": None,
        "todo_summary": {
            "total": 0,
            "checked": 0,
            "unchecked": 0,
        },
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
    state.setdefault("runner", None)
    state.setdefault("commits", [])
    state.setdefault("pending_commit", None)
    state.setdefault("current", None)
    state.setdefault(
        "todo_summary",
        {
            "total": 0,
            "checked": 0,
            "unchecked": 0,
        },
    )
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
    runner = state.get("runner")
    runner_pid = runner.get("pid") if isinstance(runner, dict) else None
    runner_alive = process_is_alive(runner_pid)
    print(f"[agent] runner: {'running' if runner_alive else 'idle'}")
    if runner_alive:
        print(f"[agent] runner pid: {runner_pid}")
        runner_started_at = runner.get("started_at")
        if runner_started_at:
            print(f"[agent] runner started at: {runner_started_at}")

    todo_summary = state.get("todo_summary", {})
    if isinstance(todo_summary, dict):
        total = todo_summary.get("total", 0)
        checked = todo_summary.get("checked", 0)
        unchecked = todo_summary.get("unchecked", 0)
        print(f"[agent] todo summary: total={total} checked={checked} unchecked={unchecked}")

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
    - [~] 已开始执行，可能未完成或被中断，可恢复
    - [x] 已完成功能
    """

    if not todo_file.exists():
        raise FileNotFoundError(f"缺少 todo 文件: {todo_file}")

    tasks = []
    occurrences = {}

    for line_no, line in enumerate(todo_file.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.match(r"^\s*-\s+\[( |~|x|X)\]\s+(.+)$", line)
        if not match:
            continue

        marker, text = match.groups()
        text = text.strip()
        occurrence = occurrences.get(text, 0) + 1
        occurrences[text] = occurrence

        tasks.append(
            {
                "id": make_task_id(todo_file, text, occurrence),
                "text": text,
                "done_in_file": marker.lower() == "x",
                "in_progress_in_file": marker == "~",
                "marker": marker,
                "line_no": line_no,
            }
        )

    return tasks


def choose_runnable_tasks(tasks, state):
    runnable = []

    for task in ordered_pending_tasks(tasks, state):
        fails = state["failed"].get(task["id"], 0)
        if fails >= MAX_FAILS_PER_TASK:
            continue

        runnable.append(task)
        if len(runnable) >= MAX_RUNNABLE_TASKS:
            break

    return runnable


def preferred_pending_task(tasks, state):
    resumable_task = None

    for task in tasks:
        if task["done_in_file"]:
            continue

        if task["id"] in state["done"]:
            continue

        if task["in_progress_in_file"]:
            resumable_task = task
            break

        if resumable_task is None:
            resumable_task = task

    return resumable_task


def ordered_pending_tasks(tasks, state):
    done_ids = set(state.get("done", []))
    resumable_tasks = []
    fresh_tasks = []

    for task in tasks:
        if task["done_in_file"]:
            continue

        if task["id"] in done_ids:
            continue

        if task["in_progress_in_file"]:
            resumable_tasks.append(task)
        else:
            fresh_tasks.append(task)

    return resumable_tasks + fresh_tasks


def choose_exhausted_tasks(tasks, state):
    exhausted = []

    for task in ordered_pending_tasks(tasks, state):
        fails = state["failed"].get(task["id"], 0)
        if fails >= MAX_FAILS_PER_TASK:
            exhausted.append(task)

    return exhausted


def reconcile_state_with_todo(state, tasks):
    checked_ids = []
    unchecked_ids = set()

    for task in tasks:
        if task["done_in_file"]:
            checked_ids.append(task["id"])
        else:
            unchecked_ids.add(task["id"])

    changed = False

    if state.get("done", []) != checked_ids:
        state["done"] = checked_ids
        changed = True

    failed = state.get("failed", {})
    if not isinstance(failed, dict):
        failed = {}

    normalized_failed = {}
    for task_id, count in failed.items():
        if task_id not in unchecked_ids:
            continue
        if not isinstance(count, int) or count <= 0:
            continue
        normalized_failed[task_id] = count

    if normalized_failed != failed:
        state["failed"] = normalized_failed
        changed = True

    todo_summary = {
        "total": len(tasks),
        "checked": len(checked_ids),
        "unchecked": len(tasks) - len(checked_ids),
    }
    if state.get("todo_summary") != todo_summary:
        state["todo_summary"] = todo_summary
        changed = True

    return changed


def set_tasks_marker(todo_file, tasks, marker):
    if not tasks:
        return {}

    original_text = todo_file.read_text(encoding="utf-8")
    lines = original_text.splitlines()
    previous_markers = {}
    changed = False

    for task in tasks:
        line_index = task["line_no"] - 1
        if line_index < 0 or line_index >= len(lines):
            continue

        current_line = lines[line_index]
        match = re.match(r"^(\s*-\s+\[)( |~|x|X)(\]\s+.*)$", current_line)
        if match is None:
            continue

        current_marker = match.group(2)
        previous_markers[task["id"]] = current_marker
        if current_marker == marker:
            continue

        lines[line_index] = f"{match.group(1)}{marker}{match.group(3)}"
        changed = True

    if changed:
        trailing_newline = "\n" if original_text.endswith("\n") else ""
        todo_file.write_text("\n".join(lines) + trailing_newline, encoding="utf-8")

    return previous_markers


def process_is_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    if process_is_zombie(pid):
        return False

    return True


def process_is_zombie(pid):
    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        stat_text = stat_path.read_text(encoding="utf-8")
    except OSError:
        return False

    _head, _sep, tail = stat_text.rpartition(")")
    if not tail:
        return False

    fields = tail.strip().split()
    if not fields:
        return False

    return fields[0] == "Z"


def runner_state():
    return {
        "pid": os.getpid(),
        "started_at": now(),
        "argv": [sys.executable, str(Path(__file__).resolve())],
    }


def register_runner(paths):
    state = load_state(paths["state_file"], paths["root"], paths["todo_file"])
    state["runner"] = runner_state()
    save_state(paths["state_file"], state)


def unregister_runner(paths):
    state = load_state(paths["state_file"], paths["root"], paths["todo_file"])
    runner = state.get("runner")
    if not isinstance(runner, dict) or runner.get("pid") != os.getpid():
        return

    state["runner"] = None
    save_state(paths["state_file"], state)


def clear_stale_runner_state(state):
    runner = state.get("runner")
    if not isinstance(runner, dict):
        return False

    if process_is_alive(runner.get("pid")):
        return False

    state["runner"] = None
    return True


def clear_stale_current_state(state):
    current = state.get("current")
    if not isinstance(current, dict):
        return False

    if process_is_alive(current.get("pid")):
        return False

    state["current"] = None
    return True


def send_signal_to_pid(pid, sig):
    try:
        os.kill(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def send_signal_to_pid_group(pid, sig):
    try:
        os.killpg(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def wait_for_process_exit(pid, timeout_seconds):
    deadline = time.monotonic() + max(0, timeout_seconds)
    while process_is_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)

    return not process_is_alive(pid)


def stop_tracked_process(pid, label, send_signal):
    if not isinstance(pid, int) or pid <= 0:
        print(f"[agent] {label}: not tracked")
        return False

    if not process_is_alive(pid):
        print(f"[agent] {label}: already stopped (pid={pid})")
        return False

    print(f"[agent] {label}: sending SIGTERM (pid={pid})")
    send_signal(pid, signal.SIGTERM)
    if wait_for_process_exit(pid, RESULT_EXIT_GRACE_SECONDS):
        print(f"[agent] {label}: stopped")
        return True

    print(f"[agent] {label}: still running, sending SIGKILL (pid={pid})")
    send_signal(pid, signal.SIGKILL)
    if wait_for_process_exit(pid, RESULT_KILL_GRACE_SECONDS):
        print(f"[agent] {label}: stopped after SIGKILL")
        return True

    print(f"[agent] {label}: failed to stop (pid={pid})")
    return False


def kill_running_agent(paths):
    state = load_state(paths["state_file"], paths["root"], paths["todo_file"])
    runner = state.get("runner")
    current = state.get("current")

    runner_pid = runner.get("pid") if isinstance(runner, dict) else None
    codex_pid = current.get("pid") if isinstance(current, dict) else None

    if runner_pid == os.getpid():
        runner_pid = None

    print(f"[agent] kill request: root={path_label(paths['root'], paths['root'])}")

    codex_stopped = stop_tracked_process(codex_pid, "codex process group", send_signal_to_pid_group)
    runner_stopped = stop_tracked_process(runner_pid, "agent_loop process", send_signal_to_pid)

    state = load_state(paths["state_file"], paths["root"], paths["todo_file"])
    changed = False

    current = state.get("current")
    if isinstance(current, dict) and current.get("pid") == codex_pid and (
        codex_stopped or not process_is_alive(codex_pid)
    ):
        state["current"] = None
        changed = True

    runner = state.get("runner")
    if isinstance(runner, dict) and runner.get("pid") == runner_pid and (
        runner_stopped or not process_is_alive(runner_pid)
    ):
        state["runner"] = None
        changed = True

    if changed:
        save_state(paths["state_file"], state)

    runner_alive = process_is_alive(runner_pid)
    codex_alive = process_is_alive(codex_pid)
    if runner_alive or codex_alive:
        return 1

    if not runner_stopped and not codex_stopped:
        print("[agent] no running agent_loop.py or codex process found")

    return 0


def is_git_repo(root):
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return probe.returncode == 0


def git_status_lines(root):
    if not is_git_repo(root):
        return []

    probe = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if probe.returncode != 0:
        return []

    return [line for line in probe.stdout.splitlines() if line.strip()]


def has_uncommitted_changes(root):
    return bool(git_status_lines(root))


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
    current_task = summarize_tasks(runnable_tasks, limit=10)
    blocked_preview = summarize_tasks(exhausted_tasks, limit=10)
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
优先恢复 todo 中已有的 `[~]` 任务，再处理新的 `[ ]` 任务；在保证质量、验证和提交纪律的前提下，本次运行要尽量多完成上面列出的可推进任务，而不是只做 1 个就停。

当前任务数：{len(runnable_tasks)}
当前因失败次数达到上限而暂时跳过的任务数：{len(exhausted_tasks)}

本轮可推进任务（按优先级顺序展示）：
{current_task}

当前已达到失败上限、需要暂时跳过的任务：
{blocked_preview}

要求：
1. 直接读取并更新 `{todo_path}`，把它当作任务真实来源。
2. 以上任务按这个优先级顺序推进：先处理 `[~]` 恢复任务，再处理新的 `[ ]` 任务；同类任务尽量保持 todo 中的原始顺序。
3. 不要只做第一个任务就停。当前一个任务真正完成后，继续推进后面的可推进任务；如果某个任务被明确阻塞，保持它为 `[~]` 并写进 `blocked`，然后继续尝试后面彼此独立、不会被它直接破坏的任务。
4. 如果后续任务显然依赖前一个未完成任务，先不要硬做依赖项；只有在确认后续任务独立可推进时，才继续处理它。
5. 对代码实现类任务强制执行 TDD：先写或补最小 failing test，再运行它确认失败，然后实现最小改动让它通过，最后做必要的重构和回归。
6. 优先复用项目里已有的测试、构建、lint、benchmark 入口；如果缺少测试基座而某个 todo 明确要求补齐，就先补最小可运行的项目级测试基座再继续。
7. 不允许作弊或偷工减料：不要用 stub、假实现、只对当前测试或 fixture 生效的硬编码、跳过断言/验证、注释掉失败路径、吞掉错误、伪造结果、伪造提交，或任何“看起来完成但实际没实现”的手段来冒充完成。
8. 最终交付必须是完整实现，不是“最小能过测试”的半成品。red/green 阶段可以先做最小改动定位问题，但结束前必须补齐必要的边界处理、错误处理、兼容性、集成逻辑和验收标准要求。
9. 必须考虑代码性能和资源开销：选择合理的数据结构与算法，避免明显的重复扫描、重复分配、不必要拷贝、无界缓存增长或其他可预见性能退化；如果当前方案有明显性能风险，先修正设计再提交。
10. 如果某个任务过大，宁可拆分复杂任务也不要提交半成品；可以在 todo 中把剩余工作拆成紧跟当前任务的更具体后续 `[ ]` 子任务，并在总结中说明拆分方案，但不得把部分实现冒充为完成。
11. 只有在某个任务真正完成并且相关验证通过后，才把对应项改成 `[x]`，并且保留原任务文本，不要改写任务描述。
12. 对暂时做不完的任务保持 `[~]`，并在总结中说明阻塞原因；但不要因为一个阻塞任务就放弃本轮其余可独立完成的任务。
13. 修改代码后必须运行相关测试、构建或最小必要验证，并且这些验证必须实际通过；只有验证通过后才允许创建提交。输出里要说明执行了哪些验证，以及 TDD 的 red/green 分别用了什么命令。如果某个验证只是 skip、mock、空跑或未覆盖真实行为，它不足以证明任务完成，你必须补充更真实的验证。
14. 如果怀疑遇到了项目工具链 bug（例如编译器、解释器、构建系统、测试运行器、包管理器本身的问题），必须在继续前把 bug 记录下来：
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
   - 被该工具链 bug 阻塞的任务必须留在 `[~]`，并写进 `blocked`。
15. 如果当前目录是 git 仓库，并且你在本轮完成了某个任务或新增了该任务相关的工具链 bug 记录，你必须在本轮结束前立即自己创建提交；不要依赖外层脚本代为提交，也不要把已勾选但未提交的任务留给下一轮。
16. 提交要求：
   - 可以在一轮里创建多个普通提交，但每个 todo 任务最多对应一个提交；不要把多个 todo 任务合并到同一次提交。
   - 提交消息要自然、简洁，能概括当前任务的真实改动，不要使用机械化模板。
   - 每次只 stage 当前要提交的那个任务直接相关的文件；如果工作区里有无关脏改动，不要把它们一起提交。
   - 不要 amend 既有提交。
17. 如果项目不是 git 仓库，也继续完成任务，并把 `commits` 留空数组。
18. 不要回退用户已有改动，不要执行 destructive git 操作，也不要扩大到和这个 todo 无关的工作。
19. 结束前必须输出一行严格单行结果，要求：
    - 这一行必须以 `{RESULT_PREFIX}` 开头
    - 前缀后面紧跟一个单行 JSON
    - JSON 示例：{{"completed":["任务1"],"blocked":["任务2"],"deferred":["任务3"],"toolchain_bugs":[".agent/toolchain-bugs/bug-report.md"],"commits":["abc1234"],"verification":["命令1"],"summary":"一句话总结"}}

字段说明：
- completed：填写本次真正完成、并且已经在 todo 文件中勾选的任务文本，可以有多个
- blocked：填写本次尝试过但暂时无法完成的任务文本，可以有多个
- deferred：默认使用空数组；不要把没有实际尝试的后续任务写进这里
- toolchain_bugs：本次新增或更新的任务相关工具链 bug 报告 markdown 路径
- commits：本次新创建的 git commit 哈希，短哈希或长哈希都可以；非 git 项目时用空数组
- verification：本次在提交前实际运行且通过的验证命令，按执行顺序填写；如果 `completed` 非空，这里必须至少有一条
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
2. 按列表顺序处理这些待补提交任务；对每个任务先重新运行它直接相关的验证命令，确认通过后，再只 stage 相关文件并立即创建一个清晰、自然的普通提交。
3. 如果只有 toolchain bug 报告待提交，也要先验证 repro 和报告内容仍然匹配，再单独提交相关文件。
4. 不要为了补提交而作弊或掩盖未完成工作：如果现有改动仍是半成品、靠硬编码或跳过验证过关、存在明显性能问题，先继续修正或恢复 todo 状态，不要创建“表面完成”的提交。
5. 不要继续实现新的 todo 任务，不要扩大工作范围，不要把多个 todo 任务合并进同一个补提交，也不要把无关脏改动一起提交。
6. 如果你发现上一个批次把 todo 勾选早了，先把错误勾选恢复成 `[~]` 或修正相关文件，再把这次修正提交掉。
7. 结束前必须输出一行严格单行结果，要求：
   - 这一行必须以 `{RESULT_PREFIX}` 开头
   - 前缀后面紧跟一个单行 JSON
   - JSON 示例：{{"completed":[],"blocked":[],"deferred":[],"toolchain_bugs":[],"commits":["abc1234"],"verification":["命令1"],"summary":"一句话总结"}}

字段说明：
- `completed`：默认使用空数组，除非这次顺手修正了 todo 状态并重新确认完成
- `blocked`：如果因为明确原因暂时无法完成补提交，写原因对应的任务文本
- `deferred`：默认使用空数组
- `toolchain_bugs`：默认使用空数组；只有这次新增或更新了 bug 报告时才填写
- `commits`：这次新创建的 git commit 哈希，短哈希或长哈希都可以
- `verification`：补提交前重新运行且通过的验证命令；如果 `commits` 非空且 `tasks` 非空，这里必须至少有一条
"""


def build_dirty_worktree_recovery_prompt(
    root,
    todo_file,
    runnable_tasks,
    exhausted_tasks,
    dirty_lines,
):
    todo_path = todo_label(root, todo_file)
    project_root = path_label(root, root)
    current_task = summarize_tasks(runnable_tasks, limit=10)
    blocked_preview = summarize_tasks(exhausted_tasks, limit=10)
    dirty_preview = summarize_strings(dirty_lines, limit=50)

    return f"""
你是一个代码执行 Agent。

当前任务的迭代被中断后，仓库里留下了未提交改动。
这次不是新的工作流，也不是额外的预处理；你是在继续“当前 todo 任务”的同一轮迭代，目标是保证当前任务验证通过并提交，然后才允许进入后续任务。

项目根目录：
{project_root}

todo 文件：
{todo_path}

当前待恢复任务：
{current_task}

当前阻塞并停止后续推进的任务：
{blocked_preview}

当前 git 脏改动：
{dirty_preview}

要求：
1. 先检查当前 git 状态、todo 勾选和未提交文件，确认这些现有改动与上面这批任务的关系。
2. 绝对不要开始新的 todo 任务；只允许围绕上面的这批待恢复任务继续收尾、补验证、补实现或补提交。
3. 不允许作弊或表面修补：不要靠硬编码、临时 stub、跳过验证、关闭断言、伪造结果或其他取巧手段让当前任务“看起来通过”。
4. 当前改动必须收敛到完整实现而不是“刚好能过”的半成品；如发现任务过大，宁可保持 `[~]` 并拆分剩余工作，也不要提交未完整实现的结果。
5. 先重新运行当前任务直接相关的验证命令；如果验证失败，继续修改当前任务相关内容直到通过，或明确判定当前任务阻塞。
6. 必须考虑代码性能和资源开销；如果当前未提交实现有明显性能缺陷或可预见退化，先修正再提交。
7. 尽量把这批任务里能完成的任务都完成；某个任务确认阻塞时，保持它为 `[~]` 并写进 `blocked`，然后继续处理后面独立可推进的任务。
8. 只有在某个任务验证通过后，才允许创建该任务对应的提交；如果一轮里补完了多个任务，可以创建多个提交，但不要把多个 todo 任务合并进同一个提交。
9. 如果某个任务还没真正完成，就不要为了“清理工作区”而做部分提交；保持它是当前任务的一部分继续迭代。
10. 如果验证通过，只 stage 当前正在提交的那个任务直接相关的现有文件，创建一个清晰、自然的普通提交。
11. 不要把当前任务和后续任务合并到同一个提交，也不要引入新的无关修改。
12. 不要回退用户已有改动，不要执行 destructive git 操作。
13. 结束前必须输出一行严格单行结果，要求：
   - 这一行必须以 `{RESULT_PREFIX}` 开头
   - 前缀后面紧跟一个单行 JSON
   - JSON 示例：{{"completed":[],"blocked":["任务文本"],"deferred":[],"toolchain_bugs":[],"commits":["abc1234"],"verification":["命令1"],"summary":"一句话总结"}}

字段说明：
- `completed`：如果你让某些任务真正完成并在 todo 中勾选，填写这些任务文本；否则用空数组
- `blocked`：如果某些任务仍然无法通过验证或暂时不能完成，填写这些任务文本或阻塞说明
- `deferred`：默认使用空数组
- `toolchain_bugs`：只有这次新增或更新了 bug 报告时才填写
- `commits`：这次为这些任务创建的新提交哈希
- `verification`：这些任务提交前实际运行且通过的验证命令；如果 `completed` 或 `commits` 非空，这里必须至少有一条
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

    cmd = build_codex_exec_command(root, prompt)

    current_task = runnable_tasks[0]["text"] if runnable_tasks else "无"
    display = LiveOutputDisplay(sys.stdout)
    log_path_text = path_label(root, log_file)

    with log_file.open("wb") as handle:
        def write_log_text(text):
            data = text.encode("utf-8", errors="replace")
            handle.write(data)
            handle.flush()
            return len(data)

        def write_log_bytes(data):
            handle.write(data)
            handle.flush()
            return len(data)

        log_size = 0
        log_size += write_log_text(f"[{now()}] START BATCH\n")
        log_size += write_log_text(f"PROJECT_ROOT: {path_label(root, root)}\n")
        log_size += write_log_text(f"TODO: {todo_label(root, todo_file)}\n")
        log_size += write_log_text(f"RUNNABLE: {len(runnable_tasks)}\n")
        log_size += write_log_text(f"EXHAUSTED: {len(exhausted_tasks)}\n\n")
        log_size += write_log_text(f"TOOLCHAIN_BUG_DIR: {path_label(root, toolchain_bug_dir)}\n")
        log_size += write_log_text(f"TOOLCHAIN_BUG_REPRO_DIR: {path_label(root, toolchain_bug_repro_dir)}\n\n")
        log_size += write_log_text(summarize_tasks(runnable_tasks, limit=50) + "\n\n")
        log_size += write_log_text("CMD: " + shlex.join(cmd[:-1]) + " <prompt>\n\n")

        display.start(current_task)

        process = None
        selector = None
        pipe_open = False
        returncode = 1

        try:
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    text=False,
                    start_new_session=True,
                )
            except FileNotFoundError:
                message = f"[{now()}] ERROR: command not found: {CODEX_CMD}\n"
                log_size += write_log_text(message)
                display.write(message)
                return False, log_file

            selector = selectors.DefaultSelector()
            if process.stdout is not None:
                selector.register(process.stdout, selectors.EVENT_READ)
                pipe_open = True

            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            scan_buffer = ""
            decoder_flushed = False

            def note_result_detected():
                nonlocal result_seen_monotonic
                if result_seen_monotonic is not None:
                    return

                result_seen_monotonic = time.monotonic()
                print(
                    "[agent] result detected: waiting briefly for codex to exit "
                    f"(grace={RESULT_EXIT_GRACE_SECONDS}s)"
                )

            def scan_result_text(text):
                nonlocal scan_buffer
                if not text or result_seen_monotonic is not None:
                    return

                scan_buffer += text
                while "\n" in scan_buffer:
                    line, scan_buffer = scan_buffer.split("\n", 1)
                    if line.rstrip("\r").startswith(RESULT_PREFIX):
                        note_result_detected()
                        return

            def flush_decoder_tail():
                nonlocal scan_buffer, decoder_flushed
                if decoder_flushed:
                    return

                tail_text = decoder.decode(b"", final=True)
                decoder_flushed = True
                if tail_text:
                    display.write(tail_text)
                    scan_result_text(tail_text)
                if scan_buffer.rstrip("\r").startswith(RESULT_PREFIX):
                    note_result_detected()
                scan_buffer = ""

            start_monotonic = time.monotonic()
            next_heartbeat = start_monotonic + HEARTBEAT_SECONDS
            last_reported_size = log_size
            last_log_size = log_size
            last_log_update_monotonic = start_monotonic
            last_log_update_at = now()
            result_seen_monotonic = None
            terminate_sent_monotonic = None

            if state is not None and state_file is not None and isinstance(state.get("current"), dict):
                state["current"]["pid"] = process.pid
                state["current"]["heartbeat_at"] = now()
                state["current"]["elapsed_seconds"] = 0
                state["current"]["log_bytes"] = last_log_size
                state["current"]["log_updated_at"] = last_log_update_at
                save_state(state_file, state)

            while True:
                current_monotonic = time.monotonic()
                heartbeat_in = max(0.0, next_heartbeat - current_monotonic)
                timeout = min(1.0, heartbeat_in) if heartbeat_in > 0 else 0.0

                if pipe_open:
                    events = selector.select(timeout)
                    for key, _mask in events:
                        chunk = os.read(key.fileobj.fileno(), 4096)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            pipe_open = False
                            continue

                        log_size += write_log_bytes(chunk)
                        last_log_size = log_size
                        last_log_update_monotonic = time.monotonic()
                        last_log_update_at = now()

                        text_chunk = decoder.decode(chunk)
                        if text_chunk:
                            display.write(text_chunk)
                            scan_result_text(text_chunk)
                elif timeout > 0:
                    time.sleep(timeout)

                current_monotonic = time.monotonic()
                returncode = process.poll()

                if not pipe_open:
                    flush_decoder_tail()

                if result_seen_monotonic is not None:
                    if (
                        terminate_sent_monotonic is None
                        and current_monotonic - result_seen_monotonic >= RESULT_EXIT_GRACE_SECONDS
                    ):
                        print("[agent] codex still running after final result; sending SIGTERM")
                        send_signal_to_process_group(process, signal.SIGTERM)
                        terminate_sent_monotonic = current_monotonic

                    if (
                        terminate_sent_monotonic is not None
                        and current_monotonic - terminate_sent_monotonic >= RESULT_KILL_GRACE_SECONDS
                    ):
                        print("[agent] codex ignored SIGTERM after final result; sending SIGKILL")
                        send_signal_to_process_group(process, signal.SIGKILL)
                        terminate_sent_monotonic = current_monotonic + 10_000

                if current_monotonic >= next_heartbeat:
                    elapsed_seconds = int(current_monotonic - start_monotonic)
                    delta_bytes = max(0, last_log_size - last_reported_size)
                    if delta_bytes > 0:
                        log_note = f"+{format_bytes(delta_bytes)} output"
                    else:
                        quiet_for = int(current_monotonic - last_log_update_monotonic)
                        log_note = f"no new output for {format_duration(quiet_for)}"

                    if display.enabled:
                        display.update(
                            current_task=current_task,
                            elapsed_seconds=elapsed_seconds,
                            log_path=log_path_text,
                            log_note=log_note,
                        )
                    else:
                        print(
                            "[agent] heartbeat: "
                            f"{format_duration(elapsed_seconds)} running | "
                            f"current={current_task} | "
                            f"log={log_path_text} | "
                            f"{log_note}"
                        )

                    if state is not None and state_file is not None and isinstance(state.get("current"), dict):
                        state["current"]["elapsed_seconds"] = elapsed_seconds
                        state["current"]["heartbeat_at"] = now()
                        state["current"]["log_bytes"] = last_log_size
                        state["current"]["log_updated_at"] = last_log_update_at
                        save_state(state_file, state)

                    last_reported_size = last_log_size
                    next_heartbeat = current_monotonic + HEARTBEAT_SECONDS

                if returncode is not None and not pipe_open:
                    elapsed_seconds = int(current_monotonic - start_monotonic)
                    if state is not None and state_file is not None and isinstance(state.get("current"), dict):
                        state["current"]["elapsed_seconds"] = elapsed_seconds
                        state["current"]["heartbeat_at"] = now()
                        state["current"]["log_bytes"] = last_log_size
                        state["current"]["log_updated_at"] = last_log_update_at
                        save_state(state_file, state)
                    break

            write_log_text(f"\n[{now()}] EXIT CODE: {returncode}\n")
        finally:
            if selector is not None:
                selector.close()
            if process is not None and process.stdout is not None:
                process.stdout.close()
            display.finish()

    return returncode == 0, log_file


def build_codex_exec_command(root, prompt):
    return [
        CODEX_CMD,
        "exec",
        "--sandbox",
        CODEX_SANDBOX,
        "--cd",
        str(root),
        prompt,
    ]


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
            "verification": normalize_string_list(result.get("verification", [])),
        }

        summary = result.get("summary", "")
        normalized["summary"] = summary.strip() if isinstance(summary, str) else ""
        return normalized

    return {}


def send_signal_to_process_group(process, sig):
    return send_signal_to_pid_group(process.pid, sig)


def restore_tasks_to_in_progress(todo_file, tasks):
    if not tasks:
        return False

    original_text = todo_file.read_text(encoding="utf-8")
    lines = original_text.splitlines()
    changed = False

    for task in tasks:
        line_index = task["line_no"] - 1
        if line_index < 0 or line_index >= len(lines):
            continue

        current_line = lines[line_index]
        updated_line = re.sub(r"^(\s*-\s+\[)(x|X)(\]\s+)", r"\1~\3", current_line, count=1)
        if updated_line == current_line:
            continue

        lines[line_index] = updated_line
        changed = True

    if not changed:
        return False

    trailing_newline = "\n" if original_text.endswith("\n") else ""
    todo_file.write_text("\n".join(lines) + trailing_newline, encoding="utf-8")
    return True


def run_verification_commands(root, commands):
    if not commands:
        return [], None

    passed = []
    for command in commands:
        print(f"[agent] verify: {command}")
        probe = subprocess.run(
            ["/bin/bash", "-lc", command],
            cwd=root,
            text=True,
        )
        if probe.returncode != 0:
            print(f"[agent] verification failed ({probe.returncode}): {command}")
            return passed, command

        passed.append(command)

    return passed, None


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
    pending_commit["tasks"] = [task["text"] for task in completed_tasks]
    pending_commit["toolchain_bug_reports"] = list(toolchain_bug_reports)
    pending_commit["attempts"] = 0
    pending_commit["updated_at"] = now()
    return pending_commit


def recovery_task_list(pending_commit):
    task_text = "提交上轮未提交改动"
    pending_tasks = pending_commit.get("tasks", [])
    if pending_tasks:
        if len(pending_tasks) == 1:
            task_text = f"提交上轮未提交改动：{pending_tasks[0]}"
        else:
            task_text = f"提交上轮未提交改动：{pending_tasks[0]} 等 {len(pending_tasks)} 项"

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
        remaining_dirty = git_status_lines(paths["root"])
        if remaining_dirty:
            print("[agent] recovery committed but worktree is still dirty; will continue recovery")
            state["current"] = None
            save_state(paths["state_file"], state)
            return False

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


def run_dirty_worktree_recovery(paths, state, runnable_tasks, exhausted_tasks):
    dirty_lines = git_status_lines(paths["root"])
    if not dirty_lines:
        return True

    recovery_tasks = list(runnable_tasks)
    recovery_log_file = make_log_file(paths["log_dir"], recovery_tasks)
    batch_head_before = git_head_commit(paths["root"])
    state["current"] = {
        "project_root": path_label(paths["root"], paths["root"]),
        "todo_file": todo_label(paths["root"], paths["todo_file"]),
        "started_at": now(),
        "task_count": len(recovery_tasks),
        "current_task": recovery_tasks[0]["text"],
        "tasks": [task["text"] for task in recovery_tasks[:20]],
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

    print("[agent] continue current task iteration from existing uncommitted changes")
    print(f"[agent] current task: {recovery_tasks[0]['text']}")
    print(f"[agent] recovery batch: {len(recovery_tasks)} task(s)")
    print_batch_preview(recovery_tasks)
    print(f"[agent] dirty entries: {len(dirty_lines)}")
    for index, line in enumerate(dirty_lines[:10], start=1):
        print(f"[agent]   {index}. {line}")

    set_tasks_marker(paths["todo_file"], recovery_tasks[:1], "~")
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
        prompt_override=build_dirty_worktree_recovery_prompt(
            paths["root"],
            paths["todo_file"],
            runnable_tasks,
            exhausted_tasks,
            dirty_lines,
        ),
    )
    result = parse_agent_result(log_file)
    verification_commands = result.get("verification", [])
    verification_failed_command = None
    verification_invalid = False

    if verification_commands:
        _passed_verification, verification_failed_command = run_verification_commands(
            paths["root"],
            verification_commands,
        )
        if verification_failed_command is not None:
            verification_invalid = True

    reported_commits = collect_valid_commits(paths["root"], result.get("commits", []))
    detected_commits = collect_new_commits(paths["root"], batch_head_before)
    commits = list(reported_commits)
    merge_unique_strings(commits, detected_commits)
    invalid_commits = len(result.get("commits", [])) - len(reported_commits)

    if commits and not verification_commands:
        print("[agent] current-task recovery produced commit without verification commands; will not continue iterating")
        verification_invalid = True

    if commits and verification_invalid:
        print("[agent] current-task recovery commit was not verification-backed; stop before advancing")
        state["current"] = None
        save_state(paths["state_file"], state)
        return False

    if invalid_commits > 0:
        print(f"[agent] current-task recovery ignored invalid commits: {invalid_commits}")

    if commits:
        print(f"[agent] current-task recovery committed: {len(commits)}")
        merge_unique_strings(state.setdefault("commits", []), commits)

    remaining_dirty = git_status_lines(paths["root"])
    if remaining_dirty:
        if verification_invalid and verification_failed_command is not None:
            print(
                "[agent] current-task recovery verification replay failed and worktree is still dirty; "
                "will retry current task"
            )
        elif not ok:
            print("[agent] current-task recovery failed and worktree is still dirty; will retry current task")
        else:
            print("[agent] current-task recovery ended but worktree is still dirty; will retry current task")

        state["current"] = None
        save_state(paths["state_file"], state)
        return False

    print("[agent] current-task recovery finished with clean worktree")
    state["current"] = None
    save_state(paths["state_file"], state)
    return True


def completed_tasks(before_tasks, after_tasks):
    after_by_id = {task["id"]: task for task in after_tasks}
    completed = []

    for task in before_tasks:
        after = after_by_id.get(task["id"])
        if after and not task["done_in_file"] and after["done_in_file"]:
            completed.append(after)

    return completed


def task_for_text(task_text, tasks):
    if not isinstance(task_text, str) or not task_text.strip():
        return None

    for task in tasks:
        if task["text"] == task_text:
            return task

    return None


def current_batch_tasks(state, tasks):
    current = state.get("current")
    if not isinstance(current, dict):
        return []

    current_tasks = match_tasks_by_text(normalize_string_list(current.get("tasks", [])), tasks)
    if current_tasks:
        return current_tasks

    current_task = task_for_text(current.get("current_task"), tasks)
    if current_task is None:
        return []

    return [current_task]


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
    todo_file = resolve_todo_file(root, args.todo)
    paths = build_runtime_paths(root, todo_file)

    if args.kill:
        return kill_running_agent(paths)

    if args.status:
        state = load_state(paths["state_file"], paths["root"], paths["todo_file"])
        if clear_stale_runner_state(state):
            save_state(paths["state_file"], state)
        if clear_stale_current_state(state):
            save_state(paths["state_file"], state)
        tasks = parse_todo(paths["todo_file"])
        if reconcile_state_with_todo(state, tasks):
            save_state(paths["state_file"], state)
        print_status(paths, state, args.status_lines)
        return 0

    ensure_gitignore(root)
    register_runner(paths)
    print(f"[agent] start: root={path_label(root, root)} todo={todo_label(root, todo_file)}")
    git_repo = is_git_repo(paths["root"])

    try:
        while True:
            state = load_state(paths["state_file"], paths["root"], paths["todo_file"])
            if clear_stale_runner_state(state):
                state["runner"] = runner_state()
                save_state(paths["state_file"], state)
            if clear_stale_current_state(state):
                save_state(paths["state_file"], state)
            tasks_before = parse_todo(paths["todo_file"])
            if reconcile_state_with_todo(state, tasks_before):
                save_state(paths["state_file"], state)

            if git_repo and isinstance(state.get("pending_commit"), dict):
                recovered = run_pending_commit_recovery(paths, state)
                if recovered:
                    continue

                time.sleep(SLEEP_SECONDS)
                continue

            runnable_tasks = choose_runnable_tasks(tasks_before, state)
            exhausted_tasks = choose_exhausted_tasks(tasks_before, state)

            recovery_tasks = current_batch_tasks(state, tasks_before) or list(runnable_tasks)

            if git_repo and has_uncommitted_changes(paths["root"]) and recovery_tasks:
                recovered = run_dirty_worktree_recovery(paths, state, recovery_tasks, exhausted_tasks)
                if recovered:
                    continue

                time.sleep(SLEEP_SECONDS)
                continue

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
            set_tasks_marker(paths["todo_file"], runnable_tasks[:1], "~")
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
            reconcile_state_with_todo(state, tasks_after)
            result = parse_agent_result(log_file)
            newly_completed = completed_tasks(tasks_before, tasks_after)
            completed_candidates = list(newly_completed)
            blocked_tasks = match_tasks_by_text(result.get("blocked", []), runnable_tasks)
            blocked_tasks = exclude_tasks(blocked_tasks, newly_completed)
            verification_commands = result.get("verification", [])
            verification_failed_command = None
            verification_invalid = False
            toolchain_bug_reports = collect_valid_toolchain_bug_reports(
                paths["root"],
                result.get("toolchain_bugs", []),
                paths["toolchain_bug_dir"],
                paths["toolchain_bug_repro_dir"],
            )
            invalid_toolchain_bug_reports = len(result.get("toolchain_bugs", [])) - len(toolchain_bug_reports)

            if completed_candidates:
                if not verification_commands:
                    print("[agent] completed task missing verification commands; keep task as in-progress")
                    verification_invalid = True
                else:
                    _passed_verification, verification_failed_command = run_verification_commands(
                        paths["root"],
                        verification_commands,
                    )
                    if verification_failed_command is not None:
                        print("[agent] completed task failed external verification replay; keep task as in-progress")
                        verification_invalid = True

                if verification_invalid:
                    if restore_tasks_to_in_progress(paths["todo_file"], completed_candidates):
                        tasks_after = parse_todo(paths["todo_file"])
                        reconcile_state_with_todo(state, tasks_after)
                    newly_completed = []

            reported_commits = collect_valid_commits(paths["root"], result.get("commits", []))
            detected_commits = collect_new_commits(paths["root"], batch_head_before)
            commits = list(reported_commits)
            merge_unique_strings(commits, detected_commits)
            invalid_commits = len(result.get("commits", [])) - len(reported_commits)

            if verification_invalid and commits:
                print("[agent] ignore commits from batch because task completion was not verification-backed")
                commits = []

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

            if verification_invalid:
                first_task = runnable_tasks[0]
                if verification_failed_command is None:
                    print(f"[agent] verification required before commit: {first_task['text']}")
                bump_failures(state, [first_task])

            if not newly_completed and not blocked_tasks and not ok and not verification_invalid:
                first_task = runnable_tasks[0]
                print(f"[agent] failed without progress: {first_task['text']}")
                bump_failures(state, [first_task])

            if not newly_completed and not blocked_tasks and ok and not verification_invalid:
                first_task = runnable_tasks[0]
                print(f"[agent] no explicit progress reported, mark failed once: {first_task['text']}")
                bump_failures(state, [first_task])

            state["current"] = None
            save_state(paths["state_file"], state)

            time.sleep(SLEEP_SECONDS)
    finally:
        unregister_runner(paths)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
