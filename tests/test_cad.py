"""
tests/test_cad.py: Tests for SolidCraft MCP client and CAD benchmark in agentr.
"""
import os
import unittest
from agentr.cad import find_solidcraft_cli, probe_solidcraft, benchmark_mount_plate, parse_stl


class TestAgentRCad(unittest.TestCase):
    def test_find_solidcraft(self):
        cli = find_solidcraft_cli()
        self.assertIsNotNone(cli, "solidcraft-cli should be located on system")
        self.assertTrue(os.path.isfile(cli))

    def test_probe_solidcraft(self):
        res = probe_solidcraft()
        self.assertNotIn("error", res)
        self.assertIn("0.28.0", res["version"])
        self.assertEqual(res["mcp_tools_count"], 19)
        self.assertEqual(res["engine_commands_count"], 553)
        self.assertTrue(res["issue_8191"]["bug_present"])
        self.assertTrue(res["issue_8191"]["sketch_line_expression"])
        self.assertFalse(res["issue_8191"]["sketch_circle_expression"])

    def test_benchmark_mount_plate(self):
        res = benchmark_mount_plate("/tmp/test-cad-bench")
        self.assertEqual(res["status"], "PASS")
        self.assertAlmostEqual(res["volume_80"]["measured"], 31243.834, places=2)
        self.assertAlmostEqual(res["volume_100"]["measured"], 39243.834, places=2)
        self.assertTrue(res["step_export"]["exists"])
        self.assertEqual(res["step_export"]["size_bytes"], 30949)
        self.assertTrue(res["stl_export"]["watertight"])
        self.assertEqual(res["stl_export"]["triangles"], 2132)


if __name__ == "__main__":
    unittest.main()
