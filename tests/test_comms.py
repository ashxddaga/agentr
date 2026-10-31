import os
import shutil
import tempfile
import unittest

from agentr.comms import (
    load_messages,
    post_message,
    get_messages_file,
    get_comms_markdown_file
)


class TestComms(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agentr_comms_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_post_and_load_messages(self):
        # 1. Post initial message
        msg1 = post_message(
            "Hello from CAD agent! Need a hand with issue 9946.",
            sender="cad-agent",
            to="@opencode",
            topic="solidcraft",
            project_dir=self.test_dir
        )
        self.assertEqual(msg1["id"], "msg-001")
        self.assertEqual(msg1["sender"], "cad-agent")
        self.assertEqual(msg1["to"], "@opencode")
        self.assertEqual(msg1["topic"], "solidcraft")

        # 2. Reply to message
        msg2 = post_message(
            "Got it! Working on single-axis align plan.",
            sender="opencode",
            to="@cad-agent",
            topic="solidcraft",
            reply_to="msg-001",
            msg_type="reply",
            project_dir=self.test_dir
        )
        self.assertEqual(msg2["id"], "msg-002")
        self.assertEqual(msg2["reply_to"], "msg-001")

        # 3. Post to different topic
        msg3 = post_message(
            "AgentR framework updated with --pane dispatch.",
            sender="agentr",
            to="@all",
            topic="infra",
            project_dir=self.test_dir
        )
        self.assertEqual(msg3["id"], "msg-003")

        # 4. Filter by topic
        sc_msgs = load_messages(project_dir=self.test_dir, topic="solidcraft")
        self.assertEqual(len(sc_msgs), 2)

        # 5. Filter by recipient
        opencode_msgs = load_messages(project_dir=self.test_dir, recipient="opencode")
        self.assertEqual(len(opencode_msgs), 2)  # msg1 (to opencode) and msg3 (to @all)

        # 6. Verify COMMS.md was generated
        md_file = get_comms_markdown_file(self.test_dir)
        self.assertTrue(os.path.exists(md_file))
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Agent Comms & Collaboration Board", content)
            self.assertIn("msg-001", content)
            self.assertIn("msg-002", content)
            self.assertIn("msg-003", content)


if __name__ == "__main__":
    unittest.main()
