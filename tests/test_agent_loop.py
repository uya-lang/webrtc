import importlib.util
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
