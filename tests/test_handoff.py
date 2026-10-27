import unittest
from agentr.adapters import get_adapter
from agentr.core import build_handoff_briefing


class TestHandoff(unittest.TestCase):

    def test_permutations_briefing_generation(self):
        agents = ["agy", "opencode", "freebuff"]
        for src in agents:
            adapter = get_adapter(src)
            self.assertIsNotNone(adapter)
            sessions = adapter.list_sessions()
            if not sessions:
                continue

            session = sessions[0]
            title, workdir, user_prompts, assistant_msgs = adapter.extract_briefing_context(
                session.cid, session.workdir
            )
            briefing, final_title, final_workdir = build_handoff_briefing(
                src, session.cid, workdir, title, user_prompts, assistant_msgs
            )

            self.assertTrue(len(briefing) > 50)
            self.assertIn(src.upper(), briefing)
            self.assertTrue(len(final_title) > 0)
            self.assertTrue(len(final_workdir) > 0)


if __name__ == "__main__":
    unittest.main()
