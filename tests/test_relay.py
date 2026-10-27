import unittest
from agentr.relay import is_rate_limit_error, get_cascade_target, find_latest_session


class TestRelay(unittest.TestCase):

    def test_is_rate_limit_error(self):
        # Truthy cases
        self.assertTrue(is_rate_limit_error("Error: 429 Too Many Requests"))
        self.assertTrue(is_rate_limit_error("RESOURCE_EXHAUSTED: quota exceeded"))
        self.assertTrue(is_rate_limit_error("You have reached your daily limit for this model"))
        self.assertTrue(is_rate_limit_error("insufficient_quota: out of credits"))
        self.assertTrue(is_rate_limit_error("rate limit reached, please try again in 4 hours"))
        self.assertTrue(is_rate_limit_error("tokens per minute exceeded"))

        # Falsy cases
        self.assertFalse(is_rate_limit_error("SyntaxError: invalid syntax on line 42"))
        self.assertFalse(is_rate_limit_error("Build succeeded in 2.4s"))
        self.assertFalse(is_rate_limit_error(""))
        self.assertFalse(is_rate_limit_error("Cannot find file foo.txt"))

    def test_get_cascade_target(self):
        cascade = ["agy", "opencode", "freebuff"]
        self.assertEqual(get_cascade_target("agy", cascade), "opencode")
        self.assertEqual(get_cascade_target("opencode", cascade), "freebuff")
        self.assertEqual(get_cascade_target("freebuff", cascade), "agy")

        # Unknown agent defaults to first in cascade
        self.assertEqual(get_cascade_target("unknown_agent", cascade), "agy")

    def test_find_latest_session(self):
        latest = find_latest_session()
        if latest:
            self.assertIsNotNone(latest.cid)
            self.assertIsNotNone(latest.agent)
            self.assertTrue(len(latest.workdir) > 0)

    def test_execute_relay_dry_run(self):
        from agentr.relay import execute_relay
        # Test dry-run execution
        success = execute_relay(dry_run=True, auto_confirm=True)
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
