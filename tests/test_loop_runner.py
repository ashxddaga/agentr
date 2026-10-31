"""
tests/test_loop_runner.py: Tests for autonomous loop runner in agentr.
"""
import os
import shutil
import tempfile
import unittest

from agentr.board import load_board, save_board, add_task, get_todo_tasks
from agentr.loop_runner import run_autonomous_queue


class TestLoopRunner(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.agentr_dir = os.path.join(self.tmpdir, ".agentr")
        os.makedirs(self.agentr_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_autonomous_queue(self):
        # Add 3 test tasks
        t1 = add_task("Task 1: Unit check", description="Check A", agent="agy", project_dir=self.tmpdir)
        t2 = add_task("Task 2: Integration check", description="Check B", agent="agy", project_dir=self.tmpdir)
        t3 = add_task("Task 3: Final validation", description="Check C", agent="agy", project_dir=self.tmpdir)

        self.assertEqual(len(get_todo_tasks(self.tmpdir)), 3)

        executed = []
        def mock_handler(task):
            executed.append(task["id"])
            return True

        processed = run_autonomous_queue(project_dir=self.tmpdir, task_handler=mock_handler)
        self.assertEqual(processed, 3)
        self.assertEqual(executed, [t1, t2, t3])
        self.assertEqual(len(get_todo_tasks(self.tmpdir)), 0)

        # Check board status
        board = load_board(self.tmpdir)
        for t in board["tasks"]:
            self.assertEqual(t["status"], "done")


if __name__ == "__main__":
    unittest.main()
