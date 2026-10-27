import unittest
from agentr.cli import resolve_session_key, get_recent_unified_lines, search_all_agents
from agentr.adapters import get_active_adapters


class TestCLI(unittest.TestCase):

    def test_get_recent_unified_lines(self):
        lines = get_recent_unified_lines()
        self.assertIsInstance(lines, list)
        if lines:
            # Each fzf line should have tab separating key and display string
            self.assertIn("\t", lines[0])

    def test_search_all_agents(self):
        # Empty or short query returns recent sessions
        recent = get_recent_unified_lines()
        search_empty = search_all_agents("")
        self.assertEqual(len(recent), len(search_empty))

    def test_resolve_session_key_passthrough(self):
        full_key = "agy:12345678:/home/user/project"
        self.assertEqual(resolve_session_key(full_key), full_key)

    def test_resolve_session_key_lookup(self):
        for adapter in get_active_adapters():
            sessions = adapter.list_sessions()
            if sessions:
                sample_session = sessions[0]
                resolved = resolve_session_key(sample_session.cid)
                self.assertIsNotNone(resolved)
                self.assertTrue(resolved.startswith(sample_session.agent + ":"))
                break


if __name__ == "__main__":
    unittest.main()
