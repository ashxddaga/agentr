import unittest
from agentr.adapters import get_adapter, get_active_adapters, get_all_adapters


class TestAdapters(unittest.TestCase):

    def test_registry(self):
        adapters = get_all_adapters()
        names = [a.name for a in adapters]
        self.assertIn("agy", names)
        self.assertIn("opencode", names)
        self.assertIn("freebuff", names)
        self.assertIn("claude", names)

    def test_detection(self):
        active = get_active_adapters()
        active_names = [a.name for a in active]
        # At least agy or freebuff or opencode should be detected on this machine
        self.assertTrue(len(active_names) > 0)

    def test_listing_sessions(self):
        active = get_active_adapters()
        for adapter in active:
            sessions = adapter.list_sessions()
            self.assertIsInstance(sessions, list)


if __name__ == "__main__":
    unittest.main()
