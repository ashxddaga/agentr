"""
agentr.board: Multi-agent project blackboard, task coordination,
              and autonomous feedback loop engine.
"""
from __future__ import annotations

import os
import json
import datetime
from typing import Optional, List, Dict, Any


from .store import find_agentr_dir, read_json_locked, write_json_locked


def get_board_dir(project_dir: Optional[str] = None) -> str:
    """Find or return the .agentr directory for a project."""
    return find_agentr_dir(project_dir)


def get_tasks_file(project_dir: Optional[str] = None) -> str:
    return os.path.join(get_board_dir(project_dir), "tasks.json")


def get_board_markdown_file(project_dir: Optional[str] = None) -> str:
    return os.path.join(get_board_dir(project_dir), "BOARD.md")


def load_board(project_dir: Optional[str] = None) -> Dict[str, Any]:
    """Load tasks and feedback data from .agentr/tasks.json."""
    tasks_file = get_tasks_file(project_dir)
    data = read_json_locked(tasks_file)
    if isinstance(data, dict):
        return data

    # Default empty board
    base = project_dir or os.getcwd()
    return {
        "project": os.path.basename(os.path.abspath(base)),
        "created_at": datetime.datetime.now().isoformat(),
        "tasks": [],
        "feedback": [],
    }


def save_board(data: Dict[str, Any], project_dir: Optional[str] = None) -> None:
    """Save tasks and feedback data, then re-render BOARD.md."""
    tasks_file = get_tasks_file(project_dir)
    write_json_locked(tasks_file, data, indent=2)

    # Re-render BOARD.md
    render_markdown_board(data, project_dir)


def render_markdown_board(data: Dict[str, Any], project_dir: Optional[str] = None) -> str:
    """Generate a clean, human- and agent-readable BOARD.md."""
    project_name = data.get("project", "Project")
    tasks = data.get("tasks", [])
    feedback = data.get("feedback", [])

    lines = [
        f"# {project_name} — Agent Coordination Board",
        "",
        "> Autonomous multi-agent coordination managed via `agentr`.",
        "",
        "## Active Task Board",
        "",
        "| ID | Task | Assigned Agent | Status | Reviewer |",
        "|---|---|:---:|:---:|:---:|",
    ]

    status_badges = {
        "todo": "⚪ To Do",
        "in_progress": "🟡 In Progress",
        "review": "🔍 In Review",
        "done": "✅ Done",
    }

    if not tasks:
        lines.append("| — | *(No active tasks. Add one with `agentr task add`)* | — | — | — |")
    else:
        for t in tasks:
            tid = t.get("id", "")
            title = t.get("title", "")
            agent = t.get("agent", "unassigned")
            status = status_badges.get(t.get("status", "todo"), t.get("status", "todo"))
            reviewer = t.get("review_by", "—")
            lines.append(f"| `{tid}` | {title} | `{agent}` | {status} | `{reviewer}` |")

    lines.extend([
        "",
        "## Agent Feedback & Improvement Loop",
        "",
    ])

    if not feedback:
        lines.append("*(No agent feedback logged yet. Log issues with `agentr feedback \"<text>\"`)*")
    else:
        for fb in feedback:
            f_agent = fb.get("agent", "agent")
            f_time = fb.get("timestamp", "")
            f_text = fb.get("text", "")
            link = f" ([GitHub Issue]({fb.get('issue_url')}))" if fb.get("issue_url") else ""
            lines.append(f"- **[{f_agent.upper()}]** *({f_time})*: {f_text}{link}")

    lines.extend([
        "",
        "---",
        "*Automated coordination powered by `agentr` · Use `agentr task --help` for commands.*",
    ])

    md_content = "\n".join(lines) + "\n"
    board_md_file = get_board_markdown_file(project_dir)
    try:
        with open(board_md_file, "w", encoding="utf-8") as f:
            f.write(md_content)
    except Exception:
        pass

    return md_content


def add_task(
    title: str,
    description: str = "",
    agent: str = "agy",
    review_by: Optional[str] = "grok",
    project_dir: Optional[str] = None,
) -> str:
    """Add a new task to the project board."""
    data = load_board(project_dir)
    tasks = data.get("tasks", [])
    task_num = len(tasks) + 1
    task_id = f"task-{task_num:02d}"

    new_task = {
        "id": task_id,
        "title": title,
        "description": description,
        "agent": agent,
        "status": "todo",
        "created_at": datetime.datetime.now().isoformat(),
        "review_by": review_by,
        "review_status": "pending",
    }
    tasks.append(new_task)
    data["tasks"] = tasks
    save_board(data, project_dir)
    return task_id


def update_task_status(
    task_id: str,
    status: str,
    project_dir: Optional[str] = None,
) -> bool:
    """Update task status ('todo', 'in_progress', 'review', 'done')."""
    data = load_board(project_dir)
    tasks = data.get("tasks", [])
    found = False
    for t in tasks:
        if t.get("id") == task_id:
            t["status"] = status
            t["updated_at"] = datetime.datetime.now().isoformat()
            found = True
            break

    if found:
        save_board(data, project_dir)
    return found


def get_todo_tasks(project_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all tasks that are currently 'todo' or 'in_progress'."""
    data = load_board(project_dir)
    return [t for t in data.get("tasks", []) if t.get("status") in ("todo", "in_progress")]


def add_feedback(
    feedback_text: str,
    agent: str = "agent",
    project_dir: Optional[str] = None,
    sync_github: bool = False,
) -> Optional[str]:
    """Log an agent feedback item into the project loop, optionally filing a GitHub issue."""
    data = load_board(project_dir)
    feedbacks = data.get("feedback", [])
    issue_url = None

    if sync_github:
        try:
            import subprocess
            import shutil
            if shutil.which("gh"):
                title = f"[{agent.upper()} Feedback] {feedback_text[:60]}"
                body = (
                    f"### Dogfood Feedback from `{agent}`\n\n"
                    f"{feedback_text}\n\n"
                    f"**Project**: `{data.get('project')}`\n"
                    f"**Timestamp**: {datetime.datetime.now().isoformat()}"
                )
                p = subprocess.run(
                    ["gh", "issue", "create", "-R", "ashxddaga/agentr", "--title", title, "--body", body],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if p.returncode == 0 and p.stdout.strip():
                    issue_url = p.stdout.strip()
        except Exception:
            pass

    entry = {
        "agent": agent,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "text": feedback_text,
    }
    if issue_url:
        entry["issue_url"] = issue_url

    feedbacks.append(entry)
    data["feedback"] = feedbacks
    save_board(data, project_dir)
    return issue_url
