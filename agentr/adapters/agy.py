"""
agentr.adapters.agy: Antigravity CLI (agy) adapter.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import sqlite3
from typing import Optional, List, Tuple

from .base import BaseAgentAdapter
from ..core import (
    SessionInfo,
    SearchResult,
    AGENT_TAGS,
    clean_text,
    highlight_matches,
)

AGY_DB = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")
AGY_BRAIN = os.path.expanduser("~/.gemini/antigravity-cli/brain")


class AgyAdapter(BaseAgentAdapter):
    name = "agy"
    display_name = "Antigravity (agy)"
    tag = AGENT_TAGS["agy"]

    def detect(self) -> bool:
        return os.path.exists(AGY_DB) or os.path.exists(AGY_BRAIN)

    def list_sessions(self) -> List[SessionInfo]:
        sessions: List[SessionInfo] = []
        if not os.path.exists(AGY_DB):
            return sessions

        try:
            conn = sqlite3.connect(AGY_DB)
            cur = conn.cursor()
            query = "SELECT conversation_id, title, preview, step_count, last_modified_time FROM conversation_summaries WHERE title != ''"
            for row in cur.execute(query):
                cid, title, prev, steps, mtime = row
                try:
                    ts = datetime.datetime.fromisoformat(mtime.replace("Z", "+00:00")).timestamp()
                    dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    ts = 0.0
                    dt_str = " " * 16
                prev_c = clean_text(prev)
                if len(prev_c) > 50:
                    prev_c = prev_c[:47] + "..."
                sessions.append(
                    SessionInfo(
                        timestamp=ts,
                        agent=self.name,
                        cid=cid,
                        dt_str=dt_str,
                        title=title,
                        step_count=steps or 0,
                        snippet=prev_c,
                        workdir="/home/ashish/Work",
                    )
                )
            conn.close()
        except Exception:
            pass

        return sessions

    def search(self, query: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        query_lower = query.strip().lower()

        meta = {}
        if os.path.exists(AGY_DB):
            try:
                conn = sqlite3.connect(AGY_DB)
                for r in conn.cursor().execute("SELECT conversation_id, title, step_count, last_modified_time FROM conversation_summaries"):
                    meta[r[0]] = (r[1], r[2], r[3])
                conn.close()
            except Exception:
                pass

        for path in glob.glob(os.path.join(AGY_BRAIN, "*", ".system_generated", "logs", "transcript.jsonl")):
            cid = path.split("/")[-4]
            title, steps, mtime = meta.get(cid, ("(Untitled)", 0, ""))
            try:
                ts = datetime.datetime.fromisoformat(mtime.replace("Z", "+00:00")).timestamp()
                dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                ts = 0.0
                dt_str = " " * 16

            snippet = ""
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if query_lower in line.lower():
                            data = json.loads(line)
                            cleaned = clean_text(data.get("content", ""))
                            idx = cleaned.lower().find(query_lower)
                            if idx != -1:
                                start = max(0, idx - 25)
                                end = min(len(cleaned), idx + len(query) + 45)
                                prefix = "..." if start > 0 else ""
                                suffix = "..." if end < len(cleaned) else ""
                                snippet = prefix + cleaned[start:end] + suffix
                                break
            except Exception:
                pass

            if (query_lower in title.lower()) or snippet:
                if not snippet:
                    snippet = f"Title match: {title}"
                results.append(
                    SearchResult(
                        timestamp=ts,
                        agent=self.name,
                        cid=cid,
                        workdir="/home/ashish/Work",
                        dt_str=dt_str,
                        title=title,
                        step_count=steps or 0,
                        snippet=snippet,
                    )
                )

        return results

    def preview(self, cid: str, query: Optional[str] = None) -> None:
        transcript_path = os.path.join(AGY_BRAIN, cid, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.exists(transcript_path):
            print("No transcript log available.")
            return

        if os.path.exists(AGY_DB):
            try:
                conn = sqlite3.connect(AGY_DB)
                cur = conn.cursor()
                row = cur.execute(
                    "SELECT title, step_count, last_modified_time FROM conversation_summaries WHERE conversation_id = ?",
                    (cid,)
                ).fetchone()
                conn.close()
                if row:
                    title, steps, mtime = row
                    date_str = mtime[:16].replace("T", " ") if mtime else ""
                    print(f"\033[1;35mAgent:\033[0m Antigravity (agy)  │  \033[1mSession:\033[0m {title}")
                    print(f"\033[90mID: {cid}  │  Date: {date_str}  │  Turns: {steps}\033[0m")
                    print("\033[90m" + "─" * 65 + "\033[0m\n")
            except Exception:
                pass

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        msg_type = data.get("type")
                        content = data.get("content", "")
                        if msg_type == "USER_INPUT":
                            clean = clean_text(content)
                            if clean:
                                hl = highlight_matches(clean, query, "36")
                                print(f"\033[1;36mYou:\033[0m \033[36m{hl}\033[0m\n")
                        elif msg_type == "PLANNER_RESPONSE" and content:
                            clean = clean_text(content)
                            if len(clean) > 350:
                                clean = clean[:350] + "..."
                            hl = highlight_matches(clean, query, "32")
                            print(f"\033[1;32mAgent:\033[0m \033[32m{hl}\033[0m\n")
                    except Exception:
                        pass
        except Exception as e:
            print(f"Error reading transcript: {e}")

    def resume(self, cid: str, workdir: str) -> None:
        if os.path.exists(workdir):
            os.chdir(workdir)
        os.execvp("agy", ["agy", "--dangerously-skip-permissions", "--conversation", cid])

    def extract_briefing_context(
        self, cid: str, workdir: str
    ) -> Tuple[str, str, List[str], List[str]]:
        title = f"AGY Session {cid}"
        user_prompts: List[str] = []
        assistant_msgs: List[str] = []

        if os.path.exists(AGY_DB):
            try:
                conn = sqlite3.connect(AGY_DB)
                cur = conn.cursor()
                r = cur.execute(
                    "SELECT title FROM conversation_summaries WHERE conversation_id = ?",
                    (cid,)
                ).fetchone()
                if r and r[0]:
                    title = r[0]
                conn.close()
            except Exception:
                pass

        t_path = os.path.join(AGY_BRAIN, cid, ".system_generated", "logs", "transcript.jsonl")
        if os.path.exists(t_path):
            try:
                with open(t_path, "r", encoding="utf-8") as f:
                    for l in f:
                        d = json.loads(l)
                        mtype = d.get("type")
                        txt = clean_text(d.get("content", ""))
                        if txt:
                            if mtype == "USER_INPUT":
                                user_prompts.append(txt)
                            elif mtype == "PLANNER_RESPONSE":
                                assistant_msgs.append(txt)
            except Exception:
                pass

        return title, workdir, user_prompts, assistant_msgs

    def receive_handoff(self, briefing: str, title: str, workdir: str) -> None:
        if os.path.exists(workdir):
            os.chdir(workdir)
        os.execvp("agy", ["agy", "--dangerously-skip-permissions", "-i", briefing])
