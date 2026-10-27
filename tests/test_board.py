import os
import shutil
import tempfile
import unittest

from agentr.board import (
    load_board,
    save_board,
    add_task,
    update_task_status,
    add_feedback,
    render_markdown_board,
    get_board_markdown_file,
)


class TestBoard(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_board_lifecycle(self):
        # 1. Initialize board and add task
        t1 = add_task("Build API endpoint", "Create /api/status", agent="opencode", review_by="grok", project_dir=self.test_dir)
        self.assertEqual(t1, "task-01")

        # 2. Add second task
        t2 = add_task("Audit security", agent="grok", project_dir=self.test_dir)
        self.assertEqual(t2, "task-02")

        # 3. Update status
        updated = update_task_status("task-01", "in_progress", project_dir=self.test_dir)
        self.assertTrue(updated)

        # 4. Add feedback
        add_feedback("Found missing CORS headers in server", agent="grok", project_dir=self.test_dir)

        # 5. Verify board data
        board = load_board(self.test_dir)
        self.assertEqual(len(board["tasks"]), 2)
        self.assertEqual(board["tasks"][0]["status"], "in_progress")
        self.assertEqual(len(board["feedback"]), 1)

        # 6. Verify BOARD.md was written
        board_md = get_board_markdown_file(self.test_dir)
        self.assertTrue(os.path.exists(board_md))
        with open(board_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("task-01", content)
        self.assertIn("Build API endpoint", content)
        self.assertIn("In Progress", content)
        self.assertIn("Found missing CORS headers", content)


if __name__ == "__main__":
    unittest.main()
