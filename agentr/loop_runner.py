"""
agentr.loop_runner: Autonomous queue worker and continuous execution loop
                    for multi-agent tasks on the agentr project blackboard.
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
from typing import Optional, List, Dict, Any, Callable

from .board import load_board, save_board, get_todo_tasks, update_task_status, add_feedback
from .adapters import get_adapter


def run_autonomous_queue(
    project_dir: Optional[str] = None,
    max_tasks: int = 50,
    task_handler: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> int:
    """
    Autonomously process tasks from the project board back-to-back until none remain.
    Returns the number of tasks successfully processed.
    """
    board = load_board(project_dir)
    project_name = board.get("project", "Project")
    print(f"\033[1;35m═══════════════════════════════════════════════════════════════\033[0m")
    print(f"\033[1;35m⚡ AGENTR AUTONOMOUS TASK RUNNER — {project_name}\033[0m")
    print(f"\033[1;35m═══════════════════════════════════════════════════════════════\033[0m\n")

    processed = 0
    while processed < max_tasks:
        todos = get_todo_tasks(project_dir)
        if not todos:
            print(f"\n\033[32m✓ All tasks on '{project_name}' board completed! Queue is empty.\033[0m")
            break

        task = todos[0]
        tid = task.get("id")
        title = task.get("title")
        agent_name = task.get("agent", "agy")
        desc = task.get("description", "")

        print(f"\n\033[1;36m▶ [{tid}] Processing:\033[0m \033[1m{title}\033[0m")
        print(f"  Assigned Agent: \033[33m{agent_name}\033[0m")
        if desc:
            print(f"  Description:    \033[90m{desc}\033[0m")

        update_task_status(tid, "in_progress", project_dir)

        success = True
        if task_handler:
            try:
                success = task_handler(task)
            except Exception as e:
                print(f"  \033[31mTask handler raised exception: {e}\033[0m")
                success = False
        else:
            # Native dispatch via adapter
            adapter = get_adapter(agent_name)
            if not adapter:
                print(f"  \033[31mUnknown agent '{agent_name}'. Skipping.\033[0m")
                update_task_status(tid, "todo", project_dir)
                break

            briefing = (
                f"You are autonomously executing task {tid}: {title}\n"
                f"Project: {project_name}\n"
                f"Details: {desc}\n\n"
                f"Complete the work required for this task. Once done, verify the outputs."
            )
            workdir = project_dir or os.getcwd()
            # Non-interactive CLI dispatch according to target agent
            if agent_name == "opencode":
                cmd = ["opencode", "--auto", "--prompt", briefing]
            elif agent_name == "grok":
                cmd = ["grok", "--always-approve", briefing]
            elif agent_name == "freebuff":
                cmd = ["freebuff", "--trust-agents"]
            else:
                # Default to agy headless / prompt mode
                cmd = ["agy", "--dangerously-skip-permissions", "-p", briefing]
            try:
                p = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=600)
                if p.returncode != 0:
                    print(f"  \033[31mAgent returned error code {p.returncode}\033[0m")
                    if p.stderr.strip():
                        print(f"  stderr: {p.stderr.strip()[:200]}")
                    success = False
                else:
                    success = True
            except Exception as e:
                print(f"  \033[31mExecution error: {e}\033[0m")
                success = False

        if success:
            update_task_status(tid, "done", project_dir)
            add_feedback(f"Task {tid} ({title}) completed autonomously by {agent_name}", agent=agent_name, project_dir=project_dir)
            print(f"  \033[32m✓ Task {tid} completed successfully.\033[0m")
            processed += 1
        else:
            update_task_status(tid, "review", project_dir)
            print(f"  \033[33m⚠ Task {tid} marked for review.\033[0m")
            processed += 1

    return processed
