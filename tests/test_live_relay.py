"""
tests/test_live_relay.py: Comprehensive unit tests for AgentR Live Relay,
                          workspace snapshot extraction, error log parsing,
                          CAD inventory tracking, and multi-agent broadcast.
"""
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agentr.live_relay import (
    extract_git_context,
    extract_error_logs,
    extract_cad_context,
    capture_live_snapshot,
    load_live_snapshot,
    format_live_briefing,
    format_live_summary,
    broadcast_live_context,
    detect_and_relay_live,
    run_live_cli,
    SNAPSHOT_DIR,
    SNAPSHOT_FILENAME,
)
from agentr.relay import is_rate_limit_error, get_cascade_target, relay_on_exhaustion


class TestLiveRelay(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agentr_live_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_dummy_stl(self, filepath: str) -> None:
        """Create a valid minimal binary STL with 1 triangle for testing."""
        header = b"\x00" * 80
        num_triangles = 1
        # Normal (0,0,1) + Vertices (0,0,0), (1,0,0), (0,1,0) + attribute byte count (0)
        tri_bytes = struct.pack("<12fH", 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0)
        with open(filepath, "wb") as f:
            f.write(header + struct.pack("<I", num_triangles) + tri_bytes)

    def test_extract_git_context_in_repo(self):
        # Current agentr directory is a git repo
        workdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        git_info = extract_git_context(workdir)
        self.assertTrue(git_info["is_repo"])
        self.assertTrue(len(git_info["branch"]) > 0)
        self.assertIn("diff_stat", git_info)
        self.assertIn("diff_patch", git_info)
        self.assertIsInstance(git_info["uncommitted_files"], list)

    def test_extract_git_context_non_repo(self):
        git_info = extract_git_context(self.test_dir)
        self.assertFalse(git_info["is_repo"])
        self.assertEqual(git_info["branch"], "")
        self.assertFalse(git_info["has_uncommitted_changes"])

    def test_extract_error_logs(self):
        # Create dummy log with cargo failure
        log_file = os.path.join(self.test_dir, "test_failure.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("running 1 test\ntest test_fillet ... FAILED\npanicked at 'assertion failed: left == right'\n")

        errors = extract_error_logs(self.test_dir)
        self.assertTrue(len(errors) >= 1)
        found = any("panicked at" in e["snippet"] for e in errors)
        self.assertTrue(found)

    def test_extract_error_logs_with_telemetry(self):
        grok_err = (
            "Error: You’ve reached your free Grok Build usage limit for now. "
            "Get SuperGrok for much higher limits, or try again later: https://grok.com/supergrok?referrer=grok-build"
        )
        errors = extract_error_logs(self.test_dir, custom_errors=[grok_err])
        self.assertTrue(len(errors) >= 1)
        self.assertEqual(errors[0]["error_type"], "RateLimitExhaustion")
        self.assertIn("Grok Build usage limit", errors[0]["snippet"])

    def test_extract_cad_context(self):
        # Create dummy CAD files
        sc_file = os.path.join(self.test_dir, "part1.sc")
        with open(sc_file, "w") as f:
            f.write("// solidcraft model\n")

        step_file = os.path.join(self.test_dir, "bracket.step")
        with open(step_file, "w") as f:
            f.write("ISO-10303-21;\n")

        stl_file = os.path.join(self.test_dir, "model.stl")
        self._create_dummy_stl(stl_file)

        cad_info = extract_cad_context(self.test_dir)
        self.assertEqual(cad_info["file_count"], 3)
        self.assertTrue(any(f["ext"] == ".step" for f in cad_info["files"]))
        self.assertTrue(any(f["ext"] == ".stl" for f in cad_info["files"]))
        self.assertTrue(any(f["ext"] == ".sc" for f in cad_info["files"]))
        self.assertIn("3 CAD files", cad_info["summary"])

    def test_capture_and_load_live_snapshot(self):
        snapshot = capture_live_snapshot(self.test_dir, save=True, task_title="CAD Fix Task")
        self.assertEqual(snapshot["workdir"], self.test_dir)
        self.assertEqual(snapshot["task_title"], "CAD Fix Task")

        snap_path = os.path.join(self.test_dir, SNAPSHOT_DIR, SNAPSHOT_FILENAME)
        self.assertTrue(os.path.isfile(snap_path))

        loaded = load_live_snapshot(self.test_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["workdir"], self.test_dir)
        self.assertEqual(loaded["task_title"], "CAD Fix Task")

    def test_format_live_briefing(self):
        snapshot = {
            "workdir": "/tmp/test-project",
            "task_title": "Issue #9939: Fillet Non-Planar Edge Chain",
            "git": {
                "branch": "fix/issue-9939",
                "has_uncommitted_changes": True,
                "diff_stat": " crates/engine/src/fillet.rs | 10 +++++++++-\n 1 file changed",
                "diff_patch": "+ // new fillet patch",
            },
            "errors": [
                {
                    "source": "cargo_test.log",
                    "error_type": "LogFileError",
                    "snippet": "FAILED tests::fillet_edges",
                }
            ],
            "cad": {
                "summary": "1 CAD model (bracket.step)",
                "files": [{"path": "bracket.step", "size_bytes": 1024}],
            },
            "session": {
                "agent": "grok",
                "cid": "ses_12345",
                "title": "Fix fillet edges",
            },
        }

        briefing = format_live_briefing(snapshot, prompt="Verify fillet non-planar chain fix")
        self.assertIn("LIVE WORKSPACE CONTEXT", briefing)
        self.assertIn("fix/issue-9939", briefing)
        self.assertIn("Verify fillet non-planar chain fix", briefing)
        self.assertIn("FAILED tests::fillet_edges", briefing)
        self.assertIn("bracket.step", briefing)
        self.assertIn("new fillet patch", briefing)

    def test_format_live_summary(self):
        snapshot = {
            "workdir": "/tmp/test-project",
            "git": {"is_repo": True, "branch": "main", "has_uncommitted_changes": False},
            "cad": {"summary": "2 CAD files"},
            "errors": [],
            "session": None,
        }
        summary = format_live_summary(snapshot)
        self.assertIn("LIVE WORKSPACE SNAPSHOT", summary)
        self.assertIn("main", summary)
        self.assertIn("2 CAD files", summary)

    def test_broadcast_live_context_dry_run(self):
        success, briefing = broadcast_live_context(
            target_agent="opencode",
            workdir=self.test_dir,
            prompt="Collaborate on CAD bugfix",
            dry_run=True,
        )
        self.assertTrue(success)
        self.assertIn("Collaborate on CAD bugfix", briefing)

        # Verify files were created
        self.assertTrue(os.path.isfile(os.path.join(self.test_dir, SNAPSHOT_DIR, "live_briefing.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.test_dir, "HANDOFF.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.test_dir, SNAPSHOT_DIR, SNAPSHOT_FILENAME)))

    def test_broadcast_invalid_target_agent(self):
        success, _ = broadcast_live_context(
            target_agent="nonexistent_agent_xyz",
            workdir=self.test_dir,
            dry_run=True,
        )
        self.assertFalse(success)

    def test_detect_and_relay_live_with_grok_telemetry(self):
        grok_telemetry = (
            "Error: You’ve reached your free Grok Build usage limit for now. "
            "Get SuperGrok for much higher limits, or try again later: https://grok.com/supergrok?referrer=grok-build"
        )
        # Test rate limit recognition
        self.assertTrue(is_rate_limit_error(grok_telemetry))

        # Test cascading target from grok
        target = get_cascade_target("grok")
        self.assertIn(target, ["opencode", "agy", "freebuff"])

        # Test automatic live relay
        relayed = detect_and_relay_live(
            error_text=grok_telemetry,
            workdir=self.test_dir,
            current_agent="grok",
            prompt="Continue fixing issue #9939",
            dry_run=True,
        )
        self.assertTrue(relayed)

        # Check relay_on_exhaustion helper in relay module
        res = relay_on_exhaustion(
            error_text=grok_telemetry,
            workdir=self.test_dir,
            current_agent="grok",
            dry_run=True,
        )
        self.assertTrue(res)

    def test_cli_snapshot_show_broadcast(self):
        # 1. snapshot
        run_live_cli(["snapshot", "--dir", self.test_dir])
        self.assertTrue(os.path.isfile(os.path.join(self.test_dir, SNAPSHOT_DIR, SNAPSHOT_FILENAME)))

        # 2. show (text & json)
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            run_live_cli(["show", "--dir", self.test_dir])
            self.assertIn("LIVE WORKSPACE SNAPSHOT", fake_out.getvalue())

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            run_live_cli(["show", "--dir", self.test_dir, "--json"])
            data = json.loads(fake_out.getvalue())
            self.assertEqual(data["workdir"], self.test_dir)

        # 3. broadcast dry-run
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            run_live_cli(["broadcast", "agy", "--prompt", "Validate fix", "--dir", self.test_dir, "--dry-run"])
            self.assertIn("AGENTR LIVE CONTEXT BROADCAST", fake_out.getvalue())
            self.assertIn("Dry-run completed", fake_out.getvalue())


if __name__ == "__main__":
    unittest.main()
