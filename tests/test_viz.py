"""
Tests for agentr.viz (swarm radar and visualizer).
"""
import os
import unittest
import tempfile
import json

from agentr.viz import get_swarm_graph_data, render_terminal_swarm, render_html_widget
from agentr.board import save_board


class TestViz(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.project_dir = self.test_dir.name
        # Seed board data
        board_data = {
            "project": "VizTestProject",
            "tasks": [
                {
                    "id": "task-01",
                    "title": "Fix CAD kernel issue",
                    "agent": "agy",
                    "status": "done"
                },
                {
                    "id": "task-02",
                    "title": "Implement feature mask",
                    "agent": "opencode",
                    "status": "in_progress"
                }
            ],
            "feedback": []
        }
        save_board(board_data, self.project_dir)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_get_swarm_graph_data(self):
        data = get_swarm_graph_data(self.project_dir)
        self.assertEqual(data["project"], "VizTestProject")
        self.assertEqual(data["stats"]["total_tasks"], 2)
        self.assertEqual(data["stats"]["completed"], 1)
        self.assertEqual(data["stats"]["in_progress"], 1)
        self.assertTrue(any(a["key"] == "agy" for a in data["agents"]))
        self.assertTrue(any(a["key"] == "opencode" for a in data["agents"]))

    def test_render_terminal_swarm(self):
        output = render_terminal_swarm(self.project_dir)
        self.assertIn("AGENTR SWARM RADAR", output)
        self.assertIn("VIZTESTPROJECT", output)
        self.assertIn("Antigravity (AGY)", output)
        self.assertIn("OpenCode (DeepSeek)", output)

    def test_render_html_widget(self):
        data = get_swarm_graph_data(self.project_dir)
        html = render_html_widget(data)
        self.assertIn("swarm-visualizer-container", html)
        self.assertIn("SWARM RADAR", html)
        self.assertIn("node-agy", html)
        self.assertIn("node-opencode", html)


if __name__ == "__main__":
    unittest.main()
