import unittest
from agentr.core import clean_text, highlight_matches, build_handoff_briefing, copy_to_clipboard


class TestCore(unittest.TestCase):

    def test_clean_text_metadata(self):
        raw = "<USER_REQUEST>\nFix the bug\n</USER_REQUEST><ADDITIONAL_METADATA>time: now</ADDITIONAL_METADATA>"
        cleaned = clean_text(raw)
        self.assertEqual(cleaned, "Fix the bug")

    def test_clean_text_empty(self):
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text("   "), "")

    def test_highlight_matches(self):
        text = "Hello world from agentr"
        res = highlight_matches(text, "world")
        self.assertIn("world", res)
        self.assertIn("\033[1;93;44m", res)

    def test_build_handoff_briefing(self):
        briefing, title, wdir = build_handoff_briefing(
            source_agent="agy",
            cid="test-uuid-1234",
            workdir="/home/ashish/Work",
            title="Refactor Architecture",
            user_prompts=["Initial prompt", "/model", "Fix error in parser"],
            assistant_msgs=["Initial response", "Parser error has been resolved successfully."],
        )
        self.assertIn("AGY", briefing)
        self.assertIn("Refactor Architecture", briefing)
        self.assertIn("Fix error in parser", briefing)
        self.assertIn("Parser error has been resolved", briefing)
        # Verify /model is not picked as last_prompt
        self.assertNotIn("• Initial Prompt: /model", briefing)


if __name__ == "__main__":
    unittest.main()
