"""
agentr.adapters.claude: Claude Code CLI adapter (experimental/roadmap).
"""
from __future__ import annotations

import glob
import json
import os
import shutil
from typing import Optional, List, Tuple

from .base import BaseAgentAdapter
from ..core import (
    SessionInfo,
    SearchResult,
    AGENT_TAGS,
    clean_text,
)

CLAUDE_DIR = os.path.expanduser("~/.claude")


class ClaudeAdapter(BaseAgentAdapter):
    name = "claude"
    display_name = "Claude Code"
    tag = AGENT_TAGS["claude"]
    is_experimental = True

    def detect(self) -> bool:
        return shutil.which("claude") is not None or os.path.exists(CLAUDE_DIR)

    def list_sessions(self) -> List[SessionInfo]:
        sessions: List[SessionInfo] = []
        if not os.path.exists(CLAUDE_DIR):
            return sessions

        # Claude Code stores project sessions under ~/.claude/projects/
        for p in glob.glob(os.path.join(CLAUDE_DIR, "projects", "*", "*.jsonl")):
            try:
                sid = os.path.splitext(os.path.basename(p))[0]
                mtime = os.path.getmtime(p)
                import datetime
                dt_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                proj_name = p.split("/")[-2]
                workdir = f"/home/ashish/{proj_name}" if os.path.exists(f"/home/ashish/{proj_name}") else "/home/ashish/Work"

                first_prompt = ""
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        data = json.loads(line)
                        if data.get("type") == "user" or data.get("role") == "user":
                            first_prompt = clean_text(data.get("content") or data.get("text") or "")
                            if first_prompt:
                                break

                title = first_prompt[:40] if first_prompt else f"Claude session in {proj_name}"
                sessions.append(
                    SessionInfo(
                        timestamp=mtime,
                        agent=self.name,
                        cid=sid,
                        dt_str=dt_str,
                        title=title,
                        step_count=0,
                        snippet=first_prompt[:50],
                        workdir=workdir,
                    )
                )
            except Exception:
                pass

        return sessions

    def search(self, query: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        query_lower = query.strip().lower()
        if not os.path.exists(CLAUDE_DIR):
            return results

        for p in glob.glob(os.path.join(CLAUDE_DIR, "projects", "*", "*.jsonl")):
            try:
                sid = os.path.splitext(os.path.basename(p))[0]
                mtime = os.path.getmtime(p)
                import datetime
                dt_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                proj_name = p.split("/")[-2]
                workdir = f"/home/ashish/{proj_name}" if os.path.exists(f"/home/ashish/{proj_name}") else "/home/ashish/Work"

                snippet = ""
                title = ""
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if query_lower in line.lower():
                            d = json.loads(line)
                            txt = clean_text(d.get("content") or d.get("text") or "")
                            idx = txt.lower().find(query_lower)
                            if idx != -1:
                                start = max(0, idx - 25)
                                end = min(len(txt), idx + len(query) + 45)
                                snippet = ("..." if start > 0 else "") + txt[start:end] + ("..." if end < len(txt) else "")
                                break

                if snippet:
                    results.append(
                        SearchResult(
                            timestamp=mtime,
                            agent=self.name,
                            cid=sid,
                            workdir=workdir,
                            dt_str=dt_str,
                            title=title or f"Claude session ({sid[:8]})",
                            step_count=0,
                            snippet=snippet,
                        )
                    )
            except Exception:
                pass

        return results

    def preview(self, cid: str, query: Optional[str] = None) -> None:
        pattern = os.path.join(CLAUDE_DIR, "projects", "*", f"{cid}.jsonl")
        matches = glob.glob(pattern)
        if not matches:
            print("Claude session transcript not found.")
            return

        with open(matches[0], "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    role = d.get("role") or d.get("type")
                    txt = clean_text(d.get("content") or d.get("text") or "")
                    if role == "user":
                        print(f"\033[1;36mYou:\033[0m {txt}\n")
                    elif role in ("assistant", "model"):
                        print(f"\033[1;31mClaude:\033[0m {txt[:350]}...\n")
                except Exception:
                    pass

    def resume(self, cid: str, workdir: str) -> None:
        if os.path.exists(workdir):
            os.chdir(workdir)
        os.execvp("claude", ["claude", "--resume", cid])

    def extract_briefing_context(
        self, cid: str, workdir: str
    ) -> Tuple[str, str, List[str], List[str]]:
        title = f"Claude Session {cid}"
        user_prompts: List[str] = []
        assistant_msgs: List[str] = []

        pattern = os.path.join(CLAUDE_DIR, "projects", "*", f"{cid}.jsonl")
        matches = glob.glob(pattern)
        if matches:
            with open(matches[0], "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        role = d.get("role") or d.get("type")
                        txt = clean_text(d.get("content") or d.get("text") or "")
                        if txt:
                            if role == "user":
                                user_prompts.append(txt)
                            elif role in ("assistant", "model"):
                                assistant_msgs.append(txt)
                    except Exception:
                        pass

        return title, workdir, user_prompts, assistant_msgs

    def receive_handoff(self, briefing: str, title: str, workdir: str) -> None:
        if os.path.exists(workdir):
            os.chdir(workdir)
        os.execvp("claude", ["claude", "-p", briefing])
