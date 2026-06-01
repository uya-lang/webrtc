import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_LOOP_PATH = REPO_ROOT / "agent_loop.py"


def load_agent_loop_module(env_updates):
    env = os.environ.copy()
    for key, value in env_updates.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    module_name = f"agent_loop_test_{abs(hash(tuple(sorted(env_updates.items()))))}"
    spec = importlib.util.spec_from_file_location(module_name, AGENT_LOOP_PATH)
    module = importlib.util.module_from_spec(spec)

    with patch.dict(os.environ, env, clear=True):
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module


class AgentLoopSandboxTests(unittest.TestCase):
    def test_default_sandbox_supports_git_writes(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        cmd = module.build_codex_exec_command(Path("/tmp/repo"), "prompt")

        self.assertEqual(
            cmd[:4],
            ["codex", "exec", "--sandbox", "danger-full-access"],
        )

    def test_explicit_sandbox_override_is_respected(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": "workspace-write"})

        cmd = module.build_codex_exec_command(Path("/tmp/repo"), "prompt")

        self.assertEqual(
            cmd[:4],
            ["codex", "exec", "--sandbox", "workspace-write"],
        )

    def test_resume_command_reuses_previous_session(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})
        session_id = "019e7d51-d947-7a12-8da8-4745674b1cf3"

        cmd = module.build_codex_exec_command(
            Path("/tmp/repo"),
            "prompt",
            resume_session_id=session_id,
        )

        self.assertEqual(
            cmd,
            [
                "codex",
                "exec",
                "--sandbox",
                "danger-full-access",
                "--cd",
                "/tmp/repo",
                "resume",
                session_id,
                "prompt",
            ],
        )

    def test_state_codex_model_is_respected(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        state = module.empty_state(Path("/tmp/project"), Path("/tmp/project/docs/todo.md"))
        state["codex_model"] = "o3"

        cmd = module.build_codex_exec_command(
            Path("/tmp/repo"),
            "prompt",
            model=module.resolve_codex_model(state),
        )

        self.assertEqual(
            cmd,
            [
                "codex",
                "exec",
                "--sandbox",
                "danger-full-access",
                "--model",
                "o3",
                "--cd",
                "/tmp/repo",
                "prompt",
            ],
        )

    def test_invalid_sandbox_still_fails_fast(self):
        with self.assertRaises(SystemExit) as excinfo:
            load_agent_loop_module({"CODEX_SANDBOX": "nope"})

        self.assertIn("unsupported CODEX_SANDBOX", str(excinfo.exception))


class AgentLoopResumeTests(unittest.TestCase):
    def test_runnable_prioritizes_in_progress_tasks_but_keeps_batch_open(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text(
                "- [ ] brand new task\n- [~] resume me first\n- [ ] later task\n",
                encoding="utf-8",
            )

            tasks = module.parse_todo(todo_file)
            state = module.empty_state(root, todo_file)
            runnable = module.choose_runnable_tasks(tasks, state)

            self.assertEqual(
                [task["text"] for task in runnable],
                ["resume me first", "brand new task", "later task"],
            )

    def test_exhausted_tasks_do_not_block_later_runnable_work(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text(
                "- [ ] brand new task\n- [~] blocked resume task\n- [ ] later task\n",
                encoding="utf-8",
            )

            tasks = module.parse_todo(todo_file)
            state = module.empty_state(root, todo_file)
            blocked_task = next(task for task in tasks if task["text"] == "blocked resume task")
            state["failed"][blocked_task["id"]] = module.MAX_FAILS_PER_TASK

            runnable = module.choose_runnable_tasks(tasks, state)
            exhausted = module.choose_exhausted_tasks(tasks, state)

            self.assertEqual(
                [task["text"] for task in runnable],
                ["brand new task", "later task"],
            )
            self.assertEqual([task["text"] for task in exhausted], ["blocked resume task"])

    def test_runnable_batch_respects_configured_limit(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None, "MAX_RUNNABLE_TASKS": "2"})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text(
                "- [~] resume me first\n- [ ] second task\n- [ ] third task\n",
                encoding="utf-8",
            )

            tasks = module.parse_todo(todo_file)
            state = module.empty_state(root, todo_file)
            runnable = module.choose_runnable_tasks(tasks, state)

            self.assertEqual([task["text"] for task in runnable], ["resume me first", "second task"])


class AgentLoopPromptTests(unittest.TestCase):
    def test_main_prompt_requires_no_shortcuts_performance_and_full_implementation(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [~] prompt task\n", encoding="utf-8")
            paths = module.build_runtime_paths(root, todo_file)
            task = module.parse_todo(todo_file)[0]

            prompt = module.build_prompt(
                root,
                todo_file,
                [task],
                [],
                paths["toolchain_bug_dir"],
                paths["toolchain_bug_repro_dir"],
            )

            self.assertIn("不允许作弊或偷工减料", prompt)
            self.assertIn("必须考虑代码性能和资源开销", prompt)
            self.assertIn("宁可拆分复杂任务也不要提交半成品", prompt)
            self.assertIn("它不足以证明任务完成", prompt)
            self.assertIn("尽量多完成上面列出的可推进任务", prompt)
            self.assertIn("不要只做第一个任务就停", prompt)
            self.assertIn("不要因为一个阻塞任务就放弃本轮其余可独立完成的任务", prompt)
            self.assertIn("同一个 codex 会话里连续推进", prompt)
            self.assertIn("先立即把它在 todo 中改成 `[~]`", prompt)

    def test_dirty_recovery_prompt_requires_full_fix_not_surface_cleanup(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [~] prompt task\n", encoding="utf-8")
            task = module.parse_todo(todo_file)[0]

            prompt = module.build_dirty_worktree_recovery_prompt(
                root,
                todo_file,
                [task],
                [],
                [" M src/example.uya"],
            )

            self.assertIn("不允许作弊或表面修补", prompt)
            self.assertIn("完整实现而不是“刚好能过”的半成品", prompt)
            self.assertIn("必须考虑代码性能和资源开销", prompt)


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class AgentLoopLiveOutputTests(unittest.TestCase):
    def test_live_output_sanitizer_handles_split_escape_sequences(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        cleaned, pending = module.sanitize_live_output_chunk("\x1b[1;", "")
        self.assertEqual(cleaned, "")
        self.assertEqual(pending, "\x1b[1;")

        cleaned, pending = module.sanitize_live_output_chunk(
            "1Hcovered\n\x1b]0;title\x07safe\n",
            pending,
        )
        self.assertEqual(cleaned, "covered\nsafe\n")
        self.assertEqual(pending, "")

    def test_live_display_uses_fixed_header_and_scroll_region_for_tty(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None, "TERM": "xterm-256color"})
        stream = FakeTTY()
        display = module.LiveOutputDisplay(stream, enabled=True)

        with patch.object(module.shutil, "get_terminal_size", return_value=os.terminal_size((60, 12))):
            display.start("实现实时输出")
            display.update(
                current_task="实现实时输出",
                elapsed_seconds=65,
                log_path=".agent/logs/current.log",
                log_note="+1.0KB output",
                force=True,
            )
            display.write("line one\nline two\n")
            display.finish()

        rendered = stream.getvalue()
        self.assertIn("\x1b[2J\x1b[H", rendered)
        self.assertIn("\x1b[5;12r", rendered)
        self.assertIn("+----------------------------------------------------------+", rendered)
        self.assertIn("| [agent] 当前任务: \x1b[32m实现实时输出\x1b[0m", rendered)
        self.assertIn("| [agent] 已运行 01:05 | 日志 .agent/logs/current.log", rendered)
        self.assertIn("line one\nline two\n", rendered)
        self.assertIn("\x1b[5;1Hline one\nline two\n", rendered)
        self.assertIn("\x1b[r", rendered)

    def test_live_display_reserves_top_row_for_vscode_terminal(self):
        module = load_agent_loop_module(
            {
                "CODEX_SANDBOX": None,
                "TERM": "xterm-256color",
                "TERM_PROGRAM": "vscode",
            }
        )
        stream = FakeTTY()
        with patch.dict(os.environ, {"TERM_PROGRAM": "vscode"}, clear=False):
            display = module.LiveOutputDisplay(stream, enabled=True)

            with patch.object(module.shutil, "get_terminal_size", return_value=os.terminal_size((60, 12))):
                display.start("实现实时输出")
                display.update(
                    current_task="实现实时输出",
                    elapsed_seconds=65,
                    log_path=".agent/logs/current.log",
                    log_note="+1.0KB output",
                    force=True,
                )
                display.write("line one\n")
                display.finish()

        rendered = stream.getvalue()
        self.assertIn("\x1b[6;11r", rendered)
        self.assertIn("\x1b[2;1H", rendered)
        self.assertIn("\x1b[3;1H", rendered)
        self.assertIn("\x1b[4;1H", rendered)
        self.assertIn("\x1b[5;1H", rendered)
        self.assertIn("\x1b[6;1Hline one\n", rendered)

    def test_live_display_reserves_footer_padding_for_busy_terminal_ui(self):
        module = load_agent_loop_module(
            {
                "CODEX_SANDBOX": None,
                "TERM": "xterm-256color",
                "AGENT_LIVE_FOOTER_BOTTOM_PADDING": "2",
            }
        )
        stream = FakeTTY()
        with patch.dict(os.environ, {"AGENT_LIVE_FOOTER_BOTTOM_PADDING": "2"}, clear=False):
            display = module.LiveOutputDisplay(stream, enabled=True)

            with patch.object(module.shutil, "get_terminal_size", return_value=os.terminal_size((60, 12))):
                display.start("实现实时输出")
                display.write("line one\n")
                display.finish()

        rendered = stream.getvalue()
        self.assertEqual(display.scroll_bottom, 10)
        self.assertIn("\x1b[5;10r", rendered)
        self.assertIn("\x1b[11;1H", rendered)
        self.assertIn("\x1b[12;1H", rendered)
        self.assertIn("\x1b[5;1Hline one\n", rendered)

    def test_live_display_restores_cursor_correctly_after_wide_output(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None, "TERM": "xterm-256color"})
        stream = FakeTTY()
        display = module.LiveOutputDisplay(stream, enabled=True)

        with patch.object(module.shutil, "get_terminal_size", return_value=os.terminal_size((20, 6))):
            display.start("宽字符输出")
            display.write("你好你好你好你好你好a")
            display.update(
                current_task="宽字符输出",
                elapsed_seconds=5,
                log_path=".agent/logs/current.log",
                log_note="+20B output",
                force=True,
            )
            display.write("tail\n")
            display.finish()

        rendered = stream.getvalue()
        self.assertIn("\x1b[6;2Htail\n", rendered)

    def test_live_display_reapplies_scroll_region_after_terminal_resize(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None, "TERM": "xterm-256color"})
        stream = FakeTTY()
        display = module.LiveOutputDisplay(stream, enabled=True)

        sizes = [
            os.terminal_size((60, 12)),
            os.terminal_size((60, 12)),
            os.terminal_size((60, 9)),
        ]
        with patch.object(module.shutil, "get_terminal_size", side_effect=sizes):
            display.start("实现实时输出")
            display.update(
                current_task="实现实时输出",
                elapsed_seconds=65,
                log_path=".agent/logs/current.log",
                log_note="+1.0KB output",
                force=True,
            )

        rendered = stream.getvalue()
        self.assertIn("\x1b[5;12r", rendered)
        self.assertIn("\x1b[5;9r", rendered)
        self.assertEqual(display.scroll_bottom, 9)

    def test_clip_display_text_uses_terminal_column_width(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        clipped = module.clip_display_text("你好世界hello", 8)

        self.assertLessEqual(module.display_text_width(clipped), 8)
        self.assertTrue(clipped.endswith("..."))

    def test_render_live_header_lines_matches_tty_width_with_border(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        lines = module.render_live_header_lines(
            "非常长的任务名称需要被裁切",
            elapsed_seconds=65,
            log_path=".agent/logs/current.log",
            log_note="+1.0KB output",
            width=20,
            color=False,
        )

        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertEqual(module.display_text_width(line), 20)
        self.assertEqual(lines[0], "+" + ("-" * 18) + "+")
        self.assertEqual(lines[-1], "+" + ("-" * 18) + "+")

    def test_live_display_does_not_forward_cursor_movement_from_child_output(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None, "TERM": "xterm-256color"})
        stream = FakeTTY()
        display = module.LiveOutputDisplay(stream, enabled=True)

        with patch.object(module.shutil, "get_terminal_size", return_value=os.terminal_size((60, 12))):
            display.start("实现实时输出")
            display.write("\x1b[1;")
            display.write("1H日志仍应留在滚动区\n")
            display.finish()

        rendered = stream.getvalue()
        self.assertNotIn("\x1b7", rendered)
        self.assertNotIn("\x1b8", rendered)
        self.assertIn("日志仍应留在滚动区\n", rendered)
        self.assertIn("\x1b[5;1H日志仍应留在滚动区\n", rendered)

    def test_live_display_falls_back_to_plain_text_when_not_using_tty_mode(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})
        stream = io.StringIO()
        display = module.LiveOutputDisplay(stream, enabled=False)

        display.start("普通输出")
        display.write("hello\n")
        display.finish()

        self.assertEqual(stream.getvalue(), "[agent] 当前任务: 普通输出\nhello\n")


class AgentLoopKillTests(unittest.TestCase):
    def test_process_is_alive_treats_zombie_as_stopped(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with patch.object(module.os, "kill", return_value=None):
            with patch.object(module, "process_is_zombie", return_value=True):
                self.assertFalse(module.process_is_alive(123))

    def test_restore_completed_tasks_to_in_progress_keeps_resume_marker(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [x] still running\n", encoding="utf-8")

            task = module.parse_todo(todo_file)[0]
            changed = module.restore_tasks_to_in_progress(todo_file, [task])

            self.assertTrue(changed)
            self.assertEqual(todo_file.read_text(encoding="utf-8"), "- [~] still running\n")

    def test_clear_stale_current_state_preserves_last_session(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})
        session_id = "019e7d51-d947-7a12-8da8-4745674b1cf3"

        state = module.empty_state(Path("/tmp/project"), Path("/tmp/project/docs/todo.md"))
        state["current"] = {
            "pid": 222,
            "current_task": "still running",
            "tasks": ["still running", "next task"],
            "task_ids": ["task-1", "task-2"],
            "log_file": ".agent/logs/current.log",
            "session_id": session_id,
        }

        with patch.object(module, "process_is_alive", return_value=False):
            cleared = module.clear_stale_current_state(state, Path("/tmp/project"))

        self.assertTrue(cleared)
        self.assertIsNone(state["current"])
        self.assertEqual(state["last_session"]["session_id"], session_id)
        self.assertEqual(state["last_session"]["current_task"], "still running")
        self.assertEqual(state["last_session"]["tasks"], ["still running", "next task"])
        self.assertEqual(state["last_session"]["task_ids"], ["task-1", "task-2"])
        self.assertEqual(state["last_session"]["log_file"], ".agent/logs/current.log")

    def test_resolve_resume_session_id_falls_back_to_latest_log(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})
        session_id = "019e7d51-d947-7a12-8da8-4745674b1cf3"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [~] still running\n", encoding="utf-8")

            paths = module.build_runtime_paths(root, todo_file)
            log_file = paths["log_dir"] / "batch-20260531-000000-stale.log"
            log_file.write_text(
                "\n".join(
                    [
                        "[2026-05-31 17:16:16] START BATCH",
                        f"session id: {session_id}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            state = module.empty_state(root, todo_file)
            resolved = module.resolve_resume_session_id(
                root,
                state,
                paths["log_dir"],
                task_texts=["still running"],
            )

        self.assertEqual(resolved, session_id)

    def test_resolve_resume_session_id_can_reuse_last_session_for_fresh_task(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})
        session_id = "019e7d51-d947-7a12-8da8-4745674b1cf3"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [ ] brand new task\n", encoding="utf-8")

            paths = module.build_runtime_paths(root, todo_file)
            state = module.empty_state(root, todo_file)
            state["last_session"] = {
                "session_id": session_id,
                "current_task": "finished previous task",
                "tasks": ["finished previous task"],
                "log_file": ".agent/logs/previous.log",
                "updated_at": "2026-05-31 17:16:16",
            }

            resolved = module.resolve_resume_session_id(
                root,
                state,
                paths["log_dir"],
                task_texts=["brand new task"],
                allow_any_known_session=True,
            )

        self.assertEqual(resolved, session_id)

    def test_todo_has_in_progress_tasks_only_counts_resume_markers(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text(
                "- [ ] fresh task\n- [~] active task\n",
                encoding="utf-8",
            )

            tasks = module.parse_todo(todo_file)

        self.assertTrue(module.todo_has_in_progress_tasks(tasks))
        self.assertFalse(
            module.todo_has_in_progress_tasks(
                [task for task in tasks if not task["in_progress_in_file"]]
            )
        )

    def test_sync_current_in_progress_tasks_from_todo_updates_current_batch(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text(
                "- [x] done task\n- [~] active task\n- [~] next active task\n- [ ] later task\n",
                encoding="utf-8",
            )

            state = module.empty_state(root, todo_file)
            state["current"] = {
                "current_task": "stale task",
                "tasks": ["stale task"],
                "task_ids": ["stale-id"],
            }

            changed = module.sync_current_in_progress_tasks_from_todo(state, todo_file)
            tasks = module.parse_todo(todo_file)
            in_progress_tasks = [task for task in tasks if task["in_progress_in_file"]]

        self.assertTrue(changed)
        self.assertEqual(state["current"]["current_task"], "active task")
        self.assertEqual(state["current"]["tasks"], ["active task", "next active task"])
        self.assertEqual(
            state["current"]["task_ids"],
            [task["id"] for task in in_progress_tasks],
        )

    def test_sync_current_in_progress_tasks_from_todo_backfills_missing_resume_marker(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text(
                "- [ ] active task\n- [ ] later task\n",
                encoding="utf-8",
            )

            tasks = module.parse_todo(todo_file)
            state = module.empty_state(root, todo_file)
            state["current"] = {
                "current_task": "active task",
                "tasks": ["active task", "later task"],
                "task_ids": [tasks[0]["id"], tasks[1]["id"]],
            }

            changed = module.sync_current_in_progress_tasks_from_todo(state, todo_file)
            todo_text = todo_file.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertEqual(
            todo_text,
            "- [~] active task\n- [ ] later task\n",
        )
        self.assertEqual(state["current"]["current_task"], "active task")
        self.assertEqual(state["current"]["tasks"], ["active task"])

    def test_sync_current_in_progress_tasks_from_todo_skips_future_batch_tasks(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text(
                "- [x] done task\n- [ ] active task\n- [ ] later task\n",
                encoding="utf-8",
            )

            tasks = module.parse_todo(todo_file)
            state = module.empty_state(root, todo_file)
            state["current"] = {
                "current_task": "done task",
                "tasks": ["done task", "active task", "later task"],
                "task_ids": [task["id"] for task in tasks],
            }

            changed = module.sync_current_in_progress_tasks_from_todo(state, todo_file)
            todo_text = todo_file.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertEqual(
            todo_text,
            "- [x] done task\n- [~] active task\n- [ ] later task\n",
        )
        self.assertEqual(state["current"]["current_task"], "active task")
        self.assertEqual(state["current"]["tasks"], ["active task"])

    def test_queue_pending_commit_keeps_all_completed_tasks(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        state = module.empty_state(Path("/tmp/project"), Path("/tmp/project/docs/todo.md"))
        completed_tasks = [
            {"text": "task one"},
            {"text": "task two"},
        ]

        module.queue_pending_commit(state, completed_tasks, ["bug.md"])

        self.assertEqual(state["pending_commit"]["tasks"], ["task one", "task two"])
        self.assertEqual(state["pending_commit"]["toolchain_bug_reports"], ["bug.md"])

    def test_load_state_discards_legacy_commits_field(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [ ] fresh task\n", encoding="utf-8")

            paths = module.build_runtime_paths(root, todo_file)
            paths["state_file"].write_text(
                json.dumps(
                    {
                        "project_root": str(root),
                        "todo_file": str(todo_file),
                        "commits": ["abc123"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            state = module.load_state(paths["state_file"], root, todo_file)

        self.assertNotIn("commits", state)

    def test_pending_commit_recovery_stays_open_when_worktree_remains_dirty(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [x] task one\n- [x] task two\n", encoding="utf-8")

            paths = module.build_runtime_paths(root, todo_file)
            state = module.empty_state(root, todo_file)
            state["pending_commit"] = {
                "tasks": ["task one", "task two"],
                "toolchain_bug_reports": [],
                "attempts": 0,
                "updated_at": "2026-05-31 12:00:00",
            }

            with patch.object(module, "git_head_commit", return_value="before"):
                with patch.object(module, "run_codex", return_value=(True, root / "fake.log")):
                    with patch.object(
                        module,
                        "parse_agent_result",
                        return_value={"commits": ["abc123"], "verification": ["make test"]},
                    ):
                        with patch.object(module, "collect_valid_commits", return_value=["abc123"]):
                            with patch.object(module, "collect_new_commits", return_value=[]):
                                with patch.object(module, "git_status_lines", return_value=[" M src/example.uya"]):
                                    recovered = module.run_pending_commit_recovery(paths, state)

            self.assertFalse(recovered)
            self.assertEqual(state["pending_commit"]["tasks"], ["task one", "task two"])
            self.assertNotIn("commits", state)

    def test_pending_commit_recovery_pushes_new_commits(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [x] task one\n- [x] task two\n", encoding="utf-8")

            paths = module.build_runtime_paths(root, todo_file)
            state = module.empty_state(root, todo_file)
            state["pending_commit"] = {
                "tasks": ["task one", "task two"],
                "toolchain_bug_reports": [],
                "attempts": 0,
                "updated_at": "2026-05-31 12:00:00",
            }

            with patch.object(module, "git_head_commit", return_value="before"):
                with patch.object(module, "run_codex", return_value=(True, root / "fake.log")):
                    with patch.object(
                        module,
                        "parse_agent_result",
                        return_value={"commits": ["abc123"], "verification": ["make test"]},
                    ):
                        with patch.object(module, "collect_valid_commits", return_value=["abc123"]):
                            with patch.object(module, "collect_new_commits", return_value=[]):
                                with patch.object(module, "git_status_lines", return_value=[]):
                                    with patch.object(
                                        module,
                                        "push_commits_to_remote",
                                        return_value=True,
                                    ) as push_mock:
                                        recovered = module.run_pending_commit_recovery(paths, state)

        self.assertTrue(recovered)
        push_mock.assert_called_once_with(paths["root"], ["abc123"])

    def test_dirty_recovery_resumes_matching_last_session(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})
        session_id = "019e7d51-d947-7a12-8da8-4745674b1cf3"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [~] still running\n", encoding="utf-8")

            paths = module.build_runtime_paths(root, todo_file)
            state = module.empty_state(root, todo_file)
            state["last_session"] = {
                "session_id": session_id,
                "current_task": "still running",
                "tasks": ["still running"],
                "log_file": ".agent/logs/previous.log",
                "updated_at": "2026-05-31 17:16:16",
            }
            runnable_tasks = module.parse_todo(todo_file)
            captured = {}

            def fake_run_codex(*args, **kwargs):
                captured["resume_session_id"] = kwargs.get("resume_session_id")
                return True, root / "fake.log"

            with patch.object(module, "git_status_lines", side_effect=[[" M src/example.uya"], []]):
                with patch.object(module, "git_head_commit", return_value="before"):
                    with patch.object(module, "run_codex", side_effect=fake_run_codex):
                        with patch.object(module, "parse_agent_result", return_value={}):
                            with patch.object(module, "collect_valid_commits", return_value=[]):
                                with patch.object(module, "collect_new_commits", return_value=[]):
                                    recovered = module.run_dirty_worktree_recovery(
                                        paths,
                                        state,
                                        runnable_tasks,
                                        [],
                                    )

        self.assertTrue(recovered)
        self.assertEqual(captured["resume_session_id"], session_id)

    def test_dirty_recovery_does_not_resume_last_session_without_resume_marker(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})
        session_id = "019e7d51-d947-7a12-8da8-4745674b1cf3"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [ ] fresh task\n", encoding="utf-8")

            paths = module.build_runtime_paths(root, todo_file)
            state = module.empty_state(root, todo_file)
            state["last_session"] = {
                "session_id": session_id,
                "current_task": "still running",
                "tasks": ["still running"],
                "log_file": ".agent/logs/previous.log",
                "updated_at": "2026-05-31 17:16:16",
            }
            runnable_tasks = module.parse_todo(todo_file)
            captured = {}

            def fake_run_codex(*args, **kwargs):
                captured["resume_session_id"] = kwargs.get("resume_session_id")
                return True, root / "fake.log"

            with patch.object(module, "git_status_lines", side_effect=[[" M src/example.uya"], []]):
                with patch.object(module, "git_head_commit", return_value="before"):
                    with patch.object(module, "run_codex", side_effect=fake_run_codex):
                        with patch.object(module, "parse_agent_result", return_value={}):
                            with patch.object(module, "collect_valid_commits", return_value=[]):
                                with patch.object(module, "collect_new_commits", return_value=[]):
                                    recovered = module.run_dirty_worktree_recovery(
                                        paths,
                                        state,
                                        runnable_tasks,
                                        [],
                                    )

        self.assertTrue(recovered)
        self.assertIsNone(captured["resume_session_id"])


class AgentLoopGitPushTests(unittest.TestCase):
    def test_push_commits_to_remote_pushes_current_branch(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            remote_repo = base / "remote.git"
            work_repo = base / "work"

            subprocess.run(["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "init", str(work_repo)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(work_repo), "checkout", "-b", "main"], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-C", str(work_repo), "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(work_repo), "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
                text=True,
            )

            (work_repo / "README.md").write_text("hello\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(work_repo), "add", "README.md"], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-C", str(work_repo), "commit", "-m", "initial commit"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(work_repo), "remote", "add", "origin", str(remote_repo)],
                check=True,
                capture_output=True,
                text=True,
            )

            head_commit = subprocess.run(
                ["git", "-C", str(work_repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            pushed = module.push_commits_to_remote(work_repo, [head_commit])

            remote_head = subprocess.run(
                ["git", "-C", str(remote_repo), "rev-parse", "main"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            upstream = subprocess.run(
                [
                    "git",
                    "-C",
                    str(work_repo),
                    "rev-parse",
                    "--abbrev-ref",
                    "--symbolic-full-name",
                    "@{u}",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        self.assertTrue(pushed)
        self.assertEqual(remote_head, head_commit)
        self.assertEqual(upstream, "origin/main")

    def test_kill_stops_runner_and_codex_and_clears_state(self):
        module = load_agent_loop_module({"CODEX_SANDBOX": None})

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "docs/todo.md"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            todo_file.write_text("- [~] still running\n", encoding="utf-8")

            paths = module.build_runtime_paths(root, todo_file)
            state = module.empty_state(root, todo_file)
            state["runner"] = {"pid": 111, "started_at": "2026-05-31 12:00:00"}
            state["current"] = {"pid": 222, "current_task": "still running"}
            module.save_state(paths["state_file"], state)

            alive = {111: True, 222: True}
            calls = []

            def fake_is_alive(pid):
                return alive.get(pid, False)

            def fake_kill(pid, sig):
                calls.append(("pid", pid, sig))
                alive[pid] = False
                return True

            def fake_killpg(pid, sig):
                calls.append(("pg", pid, sig))
                alive[pid] = False
                return True

            with patch.object(module, "process_is_alive", side_effect=fake_is_alive):
                with patch.object(module, "send_signal_to_pid", side_effect=fake_kill):
                    with patch.object(module, "send_signal_to_pid_group", side_effect=fake_killpg):
                        exit_code = module.kill_running_agent(paths)

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                calls,
                [
                    ("pg", 222, module.signal.SIGTERM),
                    ("pid", 111, module.signal.SIGTERM),
                ],
            )

            saved_state = json.loads(paths["state_file"].read_text(encoding="utf-8"))
            self.assertIsNone(saved_state["runner"])
            self.assertIsNone(saved_state["current"])
            self.assertEqual(todo_file.read_text(encoding="utf-8"), "- [~] still running\n")


if __name__ == "__main__":
    unittest.main()
