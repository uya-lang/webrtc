import importlib.util
import io
import json
import os
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

    def test_invalid_sandbox_still_fails_fast(self):
        with self.assertRaises(SystemExit) as excinfo:
            load_agent_loop_module({"CODEX_SANDBOX": "nope"})

        self.assertIn("unsupported CODEX_SANDBOX", str(excinfo.exception))


class AgentLoopResumeTests(unittest.TestCase):
    def test_runnable_prefers_first_in_progress_task_for_resume(self):
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

            self.assertEqual([task["text"] for task in runnable], ["resume me first"])

    def test_exhausted_prefers_in_progress_task_over_new_unchecked_task(self):
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

            self.assertEqual(runnable, [])
            self.assertEqual([task["text"] for task in exhausted], ["blocked resume task"])


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
        self.assertIn("\x1b[2;12r", rendered)
        self.assertIn("[agent] 当前任务: ", rendered)
        self.assertIn("\x1b[32m实现实时输出\x1b[0m", rendered)
        self.assertIn("line one\nline two\n", rendered)
        self.assertIn("\x1b[r", rendered)

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
        self.assertEqual(rendered.count("\x1b[1;1H"), 1)
        self.assertIn("日志仍应留在滚动区\n", rendered)

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
