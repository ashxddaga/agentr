"""
agentr.adapters.grok: Grok Build TUI adapter.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from typing import Optional, List, Tuple
from urllib.parse import quote

from .base import BaseAgentAdapter
from ..core import SessionInfo, SearchResult, highlight_matches, clean_text

GROK_HOME = os.path.expanduser("~/.grok")
GROK_DB = os.path.join(GROK_HOME, "sessions", "session_search.sqlite")


class GrokAdapter(BaseAgentAdapter):
    name = "grok"
    display_name = "Grok Build"
    tag = "[grok]"

    def detect(self) -> bool:
        return shutil.which("grok") is not None or os.path.exists(GROK_HOME)

    def list_sessions(self) -> List[SessionInfo]:
        sessions: List[SessionInfo] = []
        if not os.path.exists(GROK_DB):
            return sessions

        uri = f"file:{quote(os.path.abspath(GROK_DB))}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT session_id, cwd, updated_at, title, content FROM session_docs ORDER BY updated_at DESC LIMIT 50"
            )
            for row in cursor.fetchall():
                sid, cwd, updated_at, title, content = row[0], row[1], row[2], row[3], row[4]
                ts = float(updated_at)
                if ts > 1e11:
                    ts /= 1000.0

                snippet = clean_text(content)[:80] if content else "(No content)"
                sessions.append(
                    SessionInfo(
                        timestamp=ts,
                        agent=self.name,
                        cid=sid,
                        title=title or "(Untitled)",
                        workdir=cwd or os.path.expanduser("~"),
                        step_count=1,
                        preview=snippet,
                    )
                )
            conn.close()
        except Exception:
            pass

        return sessions

    def search(self, query: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        if not os.path.exists(GROK_DB):
            return results

        uri = f"file:{quote(os.path.abspath(GROK_DB))}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT session_id, cwd, updated_at, title, content FROM session_docs WHERE title LIKE ? OR content LIKE ? ORDER BY updated_at DESC LIMIT 30",
                (f"%{query}%", f"%{query}%"),
            )
            for row in cursor.fetchall():
                sid, cwd, updated_at, title, content = row[0], row[1], row[2], row[3], row[4]
                ts = float(updated_at)
                if ts > 1e11:
                    ts /= 1000.0

                cleaned = clean_text(content)
                idx = cleaned.lower().find(query.lower())
                snippet = ""
                if idx != -1:
                    start = max(0, idx - 25)
                    end = min(len(cleaned), idx + len(query) + 45)
                    prefix = "..." if start > 0 else ""
                    suffix = "..." if end < len(cleaned) else ""
                    snippet = prefix + cleaned[start:end] + suffix
                else:
                    snippet = f"Title match: {title}"

                results.append(
                    SearchResult(
                        timestamp=ts,
                        agent=self.name,
                        cid=sid,
                        title=title or "(Untitled)",
                        workdir=cwd or os.path.expanduser("~"),
                        snippet=snippet,
                    )
                )
            conn.close()
        except Exception:
            pass

        return results

    def preview(self, cid: str, query: Optional[str] = None) -> None:
        if not os.path.exists(GROK_DB):
            print("Grok session database not found.")
            return

        uri = f"file:{quote(os.path.abspath(GROK_DB))}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT cwd, updated_at, title, content FROM session_docs WHERE session_id = ?", (cid,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                print(f"Session {cid} not found.")
                return

            cwd, updated_at, title, content = row[0], row[1], row[2], row[3]
            print(f"\033[1;36m[Grok Build Session: {cid[:12]}]\033[0m")
            print(f"Title:     \033[1m{title}\033[0m")
            print(f"Directory: \033[34m{cwd}\033[0m")
            print("─" * 60)
            if content:
                print(highlight_matches(content, query) if query else content)
            else:
                print("(No transcript content available)")
        except Exception as e:
            print(f"Error previewing Grok session: {e}")

    def resume(self, cid: str, workdir: str) -> None:
        target_dir = workdir if os.path.isdir(workdir) else os.getcwd()
        os.chdir(target_dir)
        os.execvp("grok", ["grok", "-c"])

    def extract_briefing_context(
        self, cid: str, workdir: str
    ) -> Tuple[str, str, List[str], List[str]]:
        title = "Grok Task"
        user_prompts: List[str] = []
        assistant_msgs: List[str] = []

        if os.path.exists(GROK_DB):
            uri = f"file:{quote(os.path.abspath(GROK_DB))}?mode=ro"
            try:
                conn = sqlite3.connect(uri, uri=True)
                cursor = conn.cursor()
                cursor.execute("SELECT cwd, title, content FROM session_docs WHERE session_id = ?", (cid,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    if row[0]:
                        workdir = row[0]
                    if row[1]:
                        title = row[1]
                    if row[2]:
                        assistant_msgs.append(clean_text(row[2])[:1000])
            except Exception:
                pass

        return title, workdir, user_prompts, assistant_msgs

    def receive_handoff(self, briefing: str, title: str, workdir: str) -> None:
        target_dir = workdir if os.path.isdir(workdir) else os.getcwd()
        os.chdir(target_dir)
        os.execvp("grok", ["grok", briefing])
