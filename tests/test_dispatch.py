import json
import os
import unittest
from unittest.mock import patch, MagicMock

from agentr.dispatch import (
    format_teamwork_prompt,
    get_current_herdr_pane,
    dispatch_to_herdr_pane,
    dispatch_to_herdr_workspace
)


class TestDispatch(unittest.TestCase):

    def test_format_teamwork_prompt_small(self):
        prompt = format_teamwork_prompt(
            title="Fix sketch text bold toggle",
            description="Disable bold in Edit Text when font has no bold face",
            workdir="/home/ashish/Work/solidcraft",
            flavor="small"
        )
        self.assertIn("This is a single self-contained fix; keep it small and focused.", prompt)
        self.assertIn("Goal: Fix sketch text bold toggle", prompt)
        self.assertIn("Working directory: /home/ashish/Work/solidcraft", prompt)
        self.assertIn("## Requirements", prompt)
        self.assertIn("### R1. Primary Deliverable", prompt)
        self.assertIn("## Acceptance Criteria", prompt)

    def test_format_teamwork_prompt_proof_and_review(self):
        proof_prompt = format_teamwork_prompt("Prove theorem X", flavor="proof")
        self.assertIn("Use a very large team of agents.", proof_prompt)

        review_prompt = format_teamwork_prompt("Review PR #9940", flavor="review")
        self.assertIn("Review this implementation thoroughly", review_prompt)

    @patch("agentr.dispatch.subprocess.run")
    def test_get_current_herdr_pane(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": {"pane": {"pane_id": "w7:p1"}}})
        )
        pid = get_current_herdr_pane()
        self.assertEqual(pid, "w7:p1")

    @patch("agentr.dispatch.time.sleep")
    @patch("agentr.dispatch.subprocess.run")
    def test_dispatch_to_herdr_pane(self, mock_run, mock_sleep):
        # 1. split returns w7:p2
        # 2. send-text succeeds
        # 3. send-keys succeeds
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"result": {"pane": {"pane_id": "w7:p2"}}})),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout="")
        ]
        ok, new_pid = dispatch_to_herdr_pane("w7:p1", "opencode", "solve bug 9946", workdir="/tmp")
        self.assertTrue(ok)
        self.assertEqual(new_pid, "w7:p2")

    @patch("agentr.dispatch.time.sleep")
    @patch("agentr.dispatch.subprocess.run")
    def test_dispatch_to_herdr_workspace(self, mock_run, mock_sleep):
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps({
                    "result": {
                        "workspace": {"workspace_id": "ws-test"},
                        "root_pane": {"pane_id": "ws-test:p1"}
                    }
                })
            ),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout="")
        ]
        ok, ws_id, p_id = dispatch_to_herdr_workspace("TestWorker", "agy", "task briefing")
        self.assertTrue(ok)
        self.assertEqual(ws_id, "ws-test")
        self.assertEqual(p_id, "ws-test:p1")


if __name__ == "__main__":
    unittest.main()
