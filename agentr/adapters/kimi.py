"""
agentr.adapters.kimi: Kimi Code CLI adapter.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
from typing import Optional, List, Tuple

from .base import BaseAgentAdapter
from ..core import SessionInfo, SearchResult, highlight_matches, clean_text

KIMI_HOME = os.path.expanduser("~/.kimi-code")
KIMI_SESSIONS_DIR = os.path.join(KIMI_HOME, "sessions")


class KimiAdapter(BaseAgentAdapter):
    name = "kimi"
    display_name = "Kimi Code"
    tag = "[kimi]"

    def detect(self) -> bool:
        return shutil.which("kimi") is not None or os.path.exists(KIMI_HOME)

    def list_sessions(self) -> List[SessionInfo]:
        sessions: List[SessionInfo] = []
        if not os.path.exists(KIMI_SESSIONS_DIR):
            return sessions

        pattern = os.path.join(KIMI_SESSIONS_DIR, "wd_*", "session_*", "state.json")
        for state_file in glob.glob(pattern):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sid = data.get("id") or os.path.basename(os.path.dirname(state_file))
                cwd = data.get("cwd") or os.getcwd()
                title = data.get("title") or "(Untitled Kimi Session)"
                updated_at = data.get("updatedAt") or 0.0
                ts = float(updated_at)
                if ts > 1e11:
                    ts /= 1000.0

                preview = f"Kimi session in {cwd}"
                # Try reading wire.jsonl for first prompt preview
                wire_file = os.path.join(os.path.dirname(state_file), "agents", "main", "wire.jsonl")
                if os.path.exists(wire_file):
                    try:
                        with open(wire_file, "r", encoding="utf-8") as wf:
                            for line in wf:
                                try:
                                    entry = json.loads(line)
                                    content = entry.get("content") or entry.get("text") or ""
                                    if content and len(content.strip()) > 5:
                                        preview = clean_text(content)[:80]
                                        break
                                except Exception:
                                    pass
                    except Exception:
                        pass

                sessions.append(
                    SessionInfo(
                        timestamp=ts,
                        agent=self.name,
                        cid=sid,
                        title=title,
                        workdir=cwd,
                        step_count=1,
                        preview=preview,
                    )
                )
            except Exception:
                pass

        sessions.sort(key=lambda s: s.timestamp, reverse=True)
        return sessions

    def search(self, query: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        query_lower = query.lower()
        if not os.path.exists(KIMI_SESSIONS_DIR):
            return results

        pattern = os.path.join(KIMI_SESSIONS_DIR, "wd_*", "session_*", "state.json")
        for state_file in glob.glob(pattern):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sid = data.get("id") or ""
                cwd = data.get("cwd") or ""
                title = data.get("title") or "(Untitled Kimi Session)"
                updated_at = data.get("updatedAt") or 0.0
                ts = float(updated_at)
                if ts > 1e11:
                    ts /= 1000.0

                matched_snippet = ""
                if query_lower in title.lower():
                    matched_snippet = f"Title match: {title}"

                wire_file = os.path.join(os.path.dirname(state_file), "agents", "main", "wire.jsonl")
                if not matched_snippet and os.path.exists(wire_file):
                    with open(wire_file, "r", encoding="utf-8") as wf:
                        for line in wf:
                            if query_lower in line.lower():
                                cleaned = clean_text(line)
                                idx = cleaned.lower().find(query_lower)
                                start = max(0, idx - 25)
                                end = min(len(cleaned), idx + len(query) + 45)
                                matched_snippet = "..." + cleaned[start:end] + "..."
                                break

                if matched_snippet:
                    results.append(
                        SearchResult(
                            timestamp=ts,
                            agent=self.name,
                            cid=sid,
                            title=title,
                            workdir=cwd,
                            snippet=matched_snippet,
                        )
                    )
            except Exception:
                pass

        results.sort(key=lambda r: r.timestamp, reverse=True)
        return results

    def preview(self, cid: str, query: Optional[str] = None) -> None:
        pattern = os.path.join(KIMI_SESSIONS_DIR, "wd_*", f"*{cid}*", "state.json")
        matches = glob.glob(pattern)
        if not matches:
            print(f"Session {cid} not found.")
            return

        state_file = matches[0]
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cwd = data.get("cwd") or ""
            title = data.get("title") or "(Untitled Kimi Session)"
            print(f"\033[1;36m[Kimi Code Session: {cid[:12]}]\033[0m")
            print(f"Title:     \033[1m{title}\033[0m")
            print(f"Directory: \033[34m{cwd}\033[0m")
            print("─" * 60)

            wire_file = os.path.join(os.path.dirname(state_file), "agents", "main", "wire.jsonl")
            if os.path.exists(wire_file):
                with open(wire_file, "r", encoding="utf-8") as wf:
                    for line in wf:
                        cleaned = clean_text(line)
                        if query:
                            print(highlight_matches(cleaned, query))
                        else:
                            print(cleaned)
            else:
                print("(No transcript wire log available)")
        except Exception as e:
            print(f"Error previewing Kimi session: {e}")

    def resume(self, cid: str, workdir: str) -> None:
        target_dir = workdir if os.path.isdir(workdir) else os.getcwd()
        os.chdir(target_dir)
        os.execvp("kimi", ["kimi", "-S", cid])

    def extract_briefing_context(
        self, cid: str, workdir: str
    ) -> Tuple[str, str, List[str], List[str]]:
        title = "Kimi Task"
        user_prompts: List[str] = []
        assistant_msgs: List[str] = []

        pattern = os.path.join(KIMI_SESSIONS_DIR, "wd_*", f"*{cid}*", "state.json")
        matches = glob.glob(pattern)
        if matches:
            try:
                with open(matches[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                workdir = data.get("cwd") or workdir
                title = data.get("title") or title
            except Exception:
                pass

        return title, workdir, user_prompts, assistant_msgs

    def receive_handoff(self, briefing: str, title: str, workdir: str, non_interactive: bool = False, **kwargs) -> None:
        target_dir = workdir if os.path.isdir(workdir) else os.getcwd()
        os.chdir(target_dir)
        os.execvp("kimi", ["kimi", briefing])
