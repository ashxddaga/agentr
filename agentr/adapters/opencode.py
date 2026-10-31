"""
agentr.adapters.opencode: OpenCode CLI adapter (v1 & v2).
"""
from __future__ import annotations

import datetime
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

OPENCODE_DB = os.path.expanduser("~/.local/share/opencode/opencode.db")


class OpenCodeAdapter(BaseAgentAdapter):
    name = "opencode"
    display_name = "OpenCode"
    tag = AGENT_TAGS["opencode"]

    def detect(self) -> bool:
        return os.path.exists(OPENCODE_DB)

    def list_sessions(self) -> List[SessionInfo]:
        sessions: List[SessionInfo] = []
        if not os.path.exists(OPENCODE_DB):
            return sessions

        try:
            conn = sqlite3.connect(OPENCODE_DB)
            cur = conn.cursor()
            # session_v2 first
            for row in cur.execute(
                "SELECT id, title, directory, time_updated FROM session_v2 WHERE title IS NOT NULL AND title != ''"
            ):
                sid, title, directory, tu = row
                ts = tu / 1000.0 if tu else 0.0
                dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else " " * 16
                work_dir = directory or "/home/ashish/Work"
                sessions.append(
                    SessionInfo(
                        timestamp=ts,
                        agent=self.name,
                        cid=sid,
                        dt_str=dt_str,
                        title=title,
                        step_count=0,
                        snippet=work_dir,
                        workdir=work_dir,
                    )
                )

            # session (v1)
            for row in cur.execute(
                "SELECT id, title, directory, time_updated FROM session WHERE title IS NOT NULL AND title != ''"
            ):
                sid, title, directory, tu = row
                ts = tu / 1000.0 if tu else 0.0
                dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else " " * 16
                work_dir = directory or "/home/ashish/Work"
                sessions.append(
                    SessionInfo(
                        timestamp=ts,
                        agent=self.name,
                        cid=sid,
                        dt_str=dt_str,
                        title=title,
                        step_count=0,
                        snippet=work_dir,
                        workdir=work_dir,
                    )
                )
            conn.close()
        except Exception:
            pass

        return sessions

    def search(self, query: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        if not os.path.exists(OPENCODE_DB):
            return results

        query_lower = query.strip().lower()

        try:
            conn = sqlite3.connect(OPENCODE_DB)
            cur = conn.cursor()

            # Check v2
            rows_v2 = cur.execute(
                """
                SELECT s.id, s.title, s.directory, s.time_updated, sm.data
                FROM session_message sm
                JOIN session_v2 s ON sm.session_id = s.id
                WHERE sm.data LIKE ?
                GROUP BY s.id
                """,
                (f"%{query}%",),
            ).fetchall()

            for sid, title, directory, tu, mdata in rows_v2:
                ts = tu / 1000.0 if tu else 0.0
                dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else " " * 16
                workdir = directory or "/home/ashish/Work"
                snippet = ""
                try:
                    md = json.loads(mdata)
                    c = md.get("content") or md.get("text") or ""
                    if isinstance(c, list):
                        parts = []
                        for item in c:
                            if isinstance(item, dict):
                                if item.get("type") == "text" or (item.get("text") and item.get("type") != "reasoning"):
                                    parts.append(item.get("text", ""))
                            elif isinstance(item, str):
                                parts.append(item)
                        c = " ".join(parts)
                    txt = clean_text(c)
                    idx = txt.lower().find(query_lower)
                    if idx != -1:
                        start = max(0, idx - 25)
                        end = min(len(txt), idx + len(query) + 45)
                        snippet = ("..." if start > 0 else "") + txt[start:end] + ("..." if end < len(txt) else "")
                except Exception:
                    pass

                title_clean = (title or "(Untitled)")[:32]
                if not snippet:
                    snippet = f"Title match: {title_clean}"

                results.append(
                    SearchResult(
                        timestamp=ts,
                        agent=self.name,
                        cid=sid,
                        workdir=workdir,
                        dt_str=dt_str,
                        title=title_clean,
                        step_count=0,
                        snippet=snippet,
                    )
                )

            # Check v1
            rows_v1 = cur.execute(
                """
                SELECT s.id, s.title, s.directory, s.time_updated, p.data
                FROM part p
                JOIN session s ON p.session_id = s.id
                WHERE p.data LIKE ?
                GROUP BY s.id
                """,
                (f"%{query}%",),
            ).fetchall()

            for sid, title, directory, tu, pdata in rows_v1:
                ts = tu / 1000.0 if tu else 0.0
                dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else " " * 16
                workdir = directory or "/home/ashish/Work"
                snippet = ""
                try:
                    pd = json.loads(pdata)
                    txt = clean_text(pd.get("text", ""))
                    idx = txt.lower().find(query_lower)
                    if idx != -1:
                        start = max(0, idx - 25)
                        end = min(len(txt), idx + len(query) + 45)
                        snippet = ("..." if start > 0 else "") + txt[start:end] + ("..." if end < len(txt) else "")
                except Exception:
                    pass

                title_clean = (title or "(Untitled)")[:32]
                if not snippet:
                    snippet = f"Title match: {title_clean}"

                results.append(
                    SearchResult(
                        timestamp=ts,
                        agent=self.name,
                        cid=sid,
                        workdir=workdir,
                        dt_str=dt_str,
                        title=title_clean,
                        step_count=0,
                        snippet=snippet,
                    )
                )

            conn.close()
        except Exception:
            pass

        return results

    def preview(self, cid: str, query: Optional[str] = None) -> None:
        if not os.path.exists(OPENCODE_DB):
            print("OpenCode database not found.")
            return

        try:
            conn = sqlite3.connect(OPENCODE_DB)
            cur = conn.cursor()
            title, directory, tu = "", "/home/ashish/Work", 0
            s_row = cur.execute(
                "SELECT title, directory, time_updated FROM session_v2 WHERE id = ?",
                (cid,)
            ).fetchone()
            if not s_row:
                s_row = cur.execute(
                    "SELECT title, directory, time_updated FROM session WHERE id = ?",
                    (cid,)
                ).fetchone()
            if s_row:
                title, directory, tu = s_row[0] or "", s_row[1] or directory, s_row[2] or 0
                dt = datetime.datetime.fromtimestamp(tu / 1000).strftime("%Y-%m-%d %H:%M") if tu else ""
                print(f"\033[1;36mAgent:\033[0m OpenCode  │  \033[1mSession:\033[0m {title}")
                print(f"\033[90mID: {cid}  │  Date: {dt}  │  Directory: {directory}\033[0m")
                print("\033[90m" + "─" * 65 + "\033[0m\n")

            rows_v2 = cur.execute(
                "SELECT type, data FROM session_message WHERE session_id = ? ORDER BY seq ASC",
                (cid,)
            ).fetchall()

            if rows_v2:
                conn.close()
                for mtype, data in rows_v2:
                    try:
                        d = json.loads(data)
                        role = d.get("role") or d.get("sender") or mtype
                        c = d.get("content") or d.get("text") or ""
                        if isinstance(c, list):
                            parts = []
                            for item in c:
                                if isinstance(item, dict):
                                    if item.get("type") == "text" or (item.get("text") and item.get("type") != "reasoning"):
                                        parts.append(item.get("text", ""))
                                elif isinstance(item, str):
                                    parts.append(item)
                            c = " ".join(parts)
                        txt = clean_text(c)
                        if txt:
                            if role == "user":
                                hl = highlight_matches(txt, query, "36")
                                print(f"\033[1;36mYou:\033[0m \033[36m{hl}\033[0m\n")
                            else:
                                if len(txt) > 350:
                                    txt = txt[:350] + "..."
                                hl = highlight_matches(txt, query, "32")
                                print(f"\033[1;32mOpenCode:\033[0m \033[32m{hl}\033[0m\n")
                    except Exception:
                        pass
                return

            rows = cur.execute(
                """
                SELECT m.data, p.data
                FROM part p
                JOIN message m ON p.message_id = m.id
                WHERE p.session_id = ?
                ORDER BY p.time_created ASC
                """,
                (cid,),
            ).fetchall()
            conn.close()

            for m_data, p_data in rows:
                try:
                    m = json.loads(m_data)
                    p = json.loads(p_data)
                    role = m.get("role", "")
                    ptype = p.get("type")
                    if ptype == "text" and "text" in p and p["text"].strip():
                        txt = clean_text(p["text"])
                        if role == "user":
                            hl = highlight_matches(txt, query, "36")
                            print(f"\033[1;36mYou:\033[0m \033[36m{hl}\033[0m\n")
                        else:
                            if len(txt) > 350:
                                txt = txt[:350] + "..."
                            hl = highlight_matches(txt, query, "32")
                            print(f"\033[1;32mOpenCode:\033[0m \033[32m{hl}\033[0m\n")
                except Exception:
                    pass
        except Exception as e:
            print(f"Error loading OpenCode session: {e}")

    def resume(self, cid: str, workdir: str) -> None:
        if os.path.exists(workdir):
            os.chdir(workdir)
        os.execvp("opencode", ["opencode", "-s", cid])

    def extract_briefing_context(
        self, cid: str, workdir: str
    ) -> Tuple[str, str, List[str], List[str]]:
        title = f"OPENCODE Session {cid}"
        user_prompts: List[str] = []
        assistant_msgs: List[str] = []

        if os.path.exists(OPENCODE_DB):
            try:
                conn = sqlite3.connect(OPENCODE_DB)
                cur = conn.cursor()
                r = cur.execute(
                    "SELECT title, directory FROM session_v2 WHERE id = ?",
                    (cid,)
                ).fetchone()
                if not r:
                    r = cur.execute(
                        "SELECT title, directory FROM session WHERE id = ?",
                        (cid,)
                    ).fetchone()
                if r:
                    title, workdir = r[0] or title, r[1] or workdir

                rows_v2 = cur.execute(
                    "SELECT type, data FROM session_message WHERE session_id = ? ORDER BY seq ASC",
                    (cid,)
                ).fetchall()

                if rows_v2:
                    for mtype, data in rows_v2:
                        try:
                            d = json.loads(data)
                            role = d.get("role") or d.get("sender") or mtype
                            c = d.get("content") or d.get("text") or ""
                            if isinstance(c, list):
                                parts = []
                                for item in c:
                                    if isinstance(item, dict):
                                        if item.get("type") == "text" or (item.get("text") and item.get("type") != "reasoning"):
                                            parts.append(item.get("text", ""))
                                    elif isinstance(item, str):
                                        parts.append(item)
                                c = " ".join(parts)
                            txt = clean_text(c)
                            if txt:
                                if role == "user":
                                    user_prompts.append(txt)
                                else:
                                    assistant_msgs.append(txt)
                        except Exception:
                            pass
                else:
                    rows_v1 = cur.execute(
                        """
                        SELECT m.data, p.data FROM part p JOIN message m ON p.message_id = m.id
                        WHERE p.session_id = ? ORDER BY p.time_created ASC
                        """,
                        (cid,),
                    ).fetchall()
                    for md, pd in rows_v1:
                        try:
                            m = json.loads(md)
                            p = json.loads(pd)
                            role = m.get("role", "")
                            if p.get("type") == "text":
                                txt = clean_text(p.get("text", ""))
                                if txt:
                                    if role == "user":
                                        user_prompts.append(txt)
                                    else:
                                        assistant_msgs.append(txt)
                        except Exception:
                            pass
                conn.close()
            except Exception:
                pass

        return title, workdir, user_prompts, assistant_msgs

    def receive_handoff(self, briefing: str, title: str, workdir: str, non_interactive: bool = False, **kwargs) -> None:
        if os.path.exists(workdir):
            os.chdir(workdir)
        if non_interactive or os.environ.get("AGENTR_NON_INTERACTIVE") == "1":
            os.execvp("opencode", ["opencode", "run", "--auto", briefing])
        else:
            os.execvp("opencode", ["opencode", "--auto", "--prompt", briefing])
