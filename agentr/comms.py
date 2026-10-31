"""
agentr.comms: Inter-agent message board, asynchronous collaboration bus,
              and peer-to-peer notification system.
"""
from __future__ import annotations

import os
import json
import datetime
from typing import Optional, List, Dict, Any


def get_comms_dir(project_dir: Optional[str] = None) -> str:
    """Find or return the .agentr directory for messages."""
    curr = os.path.abspath(project_dir or os.getcwd())

    # Walk up to find an existing .agentr directory
    probe = curr
    while True:
        cand = os.path.join(probe, ".agentr")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent

    # If inside ~/Work, fall back to ~/Work/.agentr if it exists
    work_dir = os.path.expanduser("~/Work")
    if curr.startswith(work_dir):
        work_cand = os.path.join(work_dir, ".agentr")
        if os.path.isdir(work_cand):
            return work_cand

    return os.path.join(curr, ".agentr")


def get_messages_file(project_dir: Optional[str] = None) -> str:
    return os.path.join(get_comms_dir(project_dir), "messages.json")


def get_comms_markdown_file(project_dir: Optional[str] = None) -> str:
    return os.path.join(get_comms_dir(project_dir), "COMMS.md")


def load_messages(
    project_dir: Optional[str] = None,
    limit: Optional[int] = None,
    topic: Optional[str] = None,
    recipient: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Load messages from .agentr/messages.json with optional filters."""
    fpath = get_messages_file(project_dir)
    if not os.path.exists(fpath):
        return []

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            messages = data.get("messages", [])
    except Exception:
        return []

    # Filter by topic
    if topic and topic != "all":
        t_clean = topic.strip().lower()
        messages = [m for m in messages if m.get("topic", "").lower() == t_clean]

    # Filter by recipient
    if recipient:
        r_clean = recipient.strip().lower()
        if not r_clean.startswith("@"):
            r_clean = f"@{r_clean}"
        messages = [
            m for m in messages
            if m.get("to", "").lower() in (r_clean, "@all")
        ]

    if limit and limit > 0:
        return messages[-limit:]
    return messages


def post_message(
    body: str,
    sender: str = "agent",
    to: str = "@all",
    topic: str = "general",
    msg_type: str = "chat",
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    project_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Post a message to the agent message board and update COMMS.md."""
    comms_dir = get_comms_dir(project_dir)
    os.makedirs(comms_dir, exist_ok=True)
    fpath = get_messages_file(project_dir)

    messages = []
    project_name = os.path.basename(os.path.abspath(project_dir or os.getcwd()))
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                messages = data.get("messages", [])
                project_name = data.get("project", project_name)
        except Exception:
            messages = []

    # Generate sequential message ID
    msg_num = len(messages) + 1
    msg_id = f"msg-{msg_num:03d}"

    clean_to = to.strip()
    if clean_to and not clean_to.startswith("@"):
        clean_to = f"@{clean_to}"

    now = datetime.datetime.now()
    msg_entry = {
        "id": msg_id,
        "timestamp": now.isoformat(),
        "time_str": now.strftime("%Y-%m-%d %H:%M:%S"),
        "sender": sender.strip() or "anonymous",
        "to": clean_to or "@all",
        "topic": (topic or "general").strip().lower(),
        "type": (msg_type or "chat").strip().lower(),
        "body": body.strip(),
        "reply_to": reply_to,
        "metadata": metadata or {}
    }

    messages.append(msg_entry)

    save_payload = {
        "project": project_name,
        "updated_at": now.isoformat(),
        "total_messages": len(messages),
        "messages": messages
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(save_payload, f, indent=2)

    # Re-render COMMS.md
    render_markdown_comms(save_payload, project_dir)

    return msg_entry


def render_markdown_comms(data: Dict[str, Any], project_dir: Optional[str] = None) -> str:
    """Generate a readable, persistent COMMS.md in the project directory."""
    project_name = data.get("project", "Project")
    messages = data.get("messages", [])

    lines = [
        f"# {project_name} — Agent Comms & Collaboration Board",
        "",
        "> Asynchronous communication channel and message board for AI agents and human operators.",
        f"> Last updated: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` • Total Messages: `{len(messages)}`",
        "",
        "## Recent Communications",
        ""
    ]

    if not messages:
        lines.append("*(No messages posted yet. Use `agentr msg send` to post.)*")
    else:
        # Show recent 40 messages in reverse chronological order
        recent = list(reversed(messages[-40:]))
        for m in recent:
            mid = m.get("id")
            snd = m.get("sender")
            to = m.get("to")
            tpc = m.get("topic")
            tstr = m.get("time_str", m.get("timestamp", ""))
            body = m.get("body", "")
            mtype = (m.get("type") or "chat").upper()

            icon = "💬"
            if mtype == "BLOCKER":
                icon = "🛑"
            elif mtype == "REVIEW":
                icon = "🔍"
            elif mtype == "REQUEST":
                icon = "⚡"
            elif mtype == "HANDOFF":
                icon = "🤝"

            reply_str = f" *(reply to {m.get('reply_to')})*" if m.get("reply_to") else ""

            lines.append(f"### {icon} `[{mid}]` **@{snd}** ➔ **{to}** `#{tpc}` {reply_str}")
            lines.append(f"*Posted at: {tstr} • Type: `{mtype}`*")
            lines.append("")
            lines.append(f"{body}")
            lines.append("")
            lines.append("---")
            lines.append("")

    content = "\n".join(lines)
    md_file = get_comms_markdown_file(project_dir)
    try:
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

    return content
