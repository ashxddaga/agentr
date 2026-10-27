"""
agentr.adapters.freebuff: Freebuff CLI adapter.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import subprocess
import time
from typing import Optional, List, Tuple

from .base import BaseAgentAdapter
from ..core import (
    SessionInfo,
    SearchResult,
    AGENT_TAGS,
    clean_text,
    highlight_matches,
)

FREEBUFF_DIR = os.path.expanduser("~/.config/manicode/projects")


class FreebuffAdapter(BaseAgentAdapter):
    name = "freebuff"
    display_name = "Freebuff"
    tag = AGENT_TAGS["freebuff"]

    def detect(self) -> bool:
        return os.path.exists(FREEBUFF_DIR)

    def list_sessions(self) -> List[SessionInfo]:
        sessions: List[SessionInfo] = []
        if not os.path.exists(FREEBUFF_DIR):
            return sessions

        for p in glob.glob(os.path.join(FREEBUFF_DIR, "*", "chats", "*", "chat-meta.json")):
            try:
                parts = p.split("/")
                proj = parts[-4]
                cid = parts[-2]
                with open(p, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    prompt = clean_text(meta.get("firstPrompt", ""))
                    ts = meta.get("messagesMtimeMs", 0) / 1000.0
                    dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else " " * 16
                    steps = meta.get("messageCount", 0)

                    chat_dir = os.path.dirname(p)
                    work_dir = f"/home/ashish/{proj}" if os.path.exists(f"/home/ashish/{proj}") else "/home/ashish/Work"
                    rs_path = os.path.join(chat_dir, "run-state.json")
                    if os.path.exists(rs_path):
                        try:
                            with open(rs_path, "r", encoding="utf-8") as rf:
                                rs = json.load(rf)
                                fc = rs.get("sessionState", {}).get("fileContext", {})
                                real_root = fc.get("projectRoot") or fc.get("cwd")
                                if real_root and os.path.exists(real_root):
                                    work_dir = real_root
                        except Exception:
                            pass

                    title = prompt[:45] if prompt else f"Chat in {proj}"
                    sessions.append(
                        SessionInfo(
                            timestamp=ts,
                            agent=self.name,
                            cid=cid,
                            dt_str=dt_str,
                            title=title,
                            step_count=steps,
                            snippet=prompt[:50],
                            workdir=work_dir,
                        )
                    )
            except Exception:
                pass

        return sessions

    def search(self, query: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        if not os.path.exists(FREEBUFF_DIR):
            return results

        query_lower = query.strip().lower()
        rg_cmd = ["rg", "-i", "-l", query, FREEBUFF_DIR]
        matched_files: List[str] = []

        try:
            p = subprocess.run(rg_cmd, capture_output=True, text=True)
            if p.returncode == 0:
                matched_files = [
                    f for f in p.stdout.splitlines()
                    if f.endswith("chat-messages.json") or f.endswith("chat-meta.json")
                ]
        except Exception:
            matched_files = glob.glob(os.path.join(FREEBUFF_DIR, "*", "chats", "*", "chat-messages.json"))

        seen_cids = set()
        for fpath in matched_files:
            parts = fpath.split("/")
            if len(parts) < 4:
                continue
            proj = parts[-4]
            cid = parts[-2]
            if cid in seen_cids:
                continue
            seen_cids.add(cid)

            chat_dir = os.path.dirname(fpath)
            meta_path = os.path.join(chat_dir, "chat-meta.json")
            msgs_path = os.path.join(chat_dir, "chat-messages.json")
            rs_path = os.path.join(chat_dir, "run-state.json")

            ts = 0.0
            steps = 0
            title = f"Chat in {proj}"

            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as mf:
                        meta = json.load(mf)
                        ts = meta.get("messagesMtimeMs", 0) / 1000.0
                        steps = meta.get("messageCount", 0)
                        pr = clean_text(meta.get("firstPrompt", ""))
                        if pr:
                            title = pr[:40]
                except Exception:
                    pass

            dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else " " * 16
            workdir = f"/home/ashish/{proj}" if os.path.exists(f"/home/ashish/{proj}") else "/home/ashish/Work"
            if os.path.exists(rs_path):
                try:
                    with open(rs_path, "r", encoding="utf-8") as rf:
                        rs = json.load(rf)
                        fc = rs.get("sessionState", {}).get("fileContext", {})
                        real_root = fc.get("projectRoot") or fc.get("cwd")
                        if real_root and os.path.exists(real_root):
                            workdir = real_root
                except Exception:
                    pass

            snippet = ""
            if os.path.exists(msgs_path):
                try:
                    with open(msgs_path, "r", encoding="utf-8") as msf:
                        msgs = json.load(msf)
                        for m in msgs:
                            c = clean_text(m.get("content", ""))
                            if query_lower in c.lower():
                                idx = c.lower().find(query_lower)
                                start = max(0, idx - 25)
                                end = min(len(c), idx + len(query) + 45)
                                snippet = ("..." if start > 0 else "") + c[start:end] + ("..." if end < len(c) else "")
                                break
                            for b in m.get("blocks", []):
                                bt = clean_text(b.get("content") or b.get("text") or "")
                                if query_lower in bt.lower():
                                    idx = bt.lower().find(query_lower)
                                    start = max(0, idx - 25)
                                    end = min(len(bt), idx + len(query) + 45)
                                    snippet = ("..." if start > 0 else "") + bt[start:end] + ("..." if end < len(bt) else "")
                                    break
                            if snippet:
                                break
                except Exception:
                    pass

            if not snippet:
                snippet = f"Match in {proj}"

            results.append(
                SearchResult(
                    timestamp=ts,
                    agent=self.name,
                    cid=cid,
                    workdir=workdir,
                    dt_str=dt_str,
                    title=title,
                    step_count=steps,
                    snippet=snippet,
                )
            )

        return results

    def preview(self, cid: str, query: Optional[str] = None) -> None:
        pattern = os.path.join(FREEBUFF_DIR, "*", "chats", cid)
        matches = glob.glob(pattern)
        if not matches:
            print("Freebuff chat folder not found.")
            return

        chat_dir = matches[0]
        meta_path = os.path.join(chat_dir, "chat-meta.json")
        msgs_path = os.path.join(chat_dir, "chat-messages.json")

        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    mtime_ms = meta.get("messagesMtimeMs", 0)
                    dt = datetime.datetime.fromtimestamp(mtime_ms / 1000).strftime("%Y-%m-%d %H:%M") if mtime_ms else ""
                    proj = chat_dir.split("/")[-3]
                    print(f"\033[1;33mAgent:\033[0m Freebuff  │  \033[1mProject:\033[0m {proj}")
                    print(f"\033[90mID: {cid}  │  Date: {dt}  │  Messages: {meta.get('messageCount', 0)}\033[0m")
                    print("\033[90m" + "─" * 65 + "\033[0m\n")
            except Exception:
                pass

        if os.path.exists(msgs_path):
            try:
                with open(msgs_path, "r", encoding="utf-8") as f:
                    msgs = json.load(f)
                    for m in msgs:
                        variant = m.get("variant", "")
                        content = m.get("content", "")
                        if content:
                            clean = clean_text(content)
                            if variant == "user":
                                hl = highlight_matches(clean, query, "36")
                                print(f"\033[1;36mYou:\033[0m \033[36m{hl}\033[0m\n")
                            else:
                                if len(clean) > 350:
                                    clean = clean[:350] + "..."
                                hl = highlight_matches(clean, query, "32")
                                print(f"\033[1;32mFreebuff:\033[0m \033[32m{hl}\033[0m\n")
                        for b in m.get("blocks", []):
                            if b.get("type") == "text" and b.get("textType") != "reasoning":
                                t = b.get("content") or b.get("text") or ""
                                if t.strip():
                                    clean = clean_text(t)
                                    if len(clean) > 350:
                                        clean = clean[:350] + "..."
                                    hl = highlight_matches(clean, query, "32")
                                    print(f"\033[1;32mFreebuff:\033[0m \033[32m{hl}\033[0m\n")
            except Exception as e:
                print(f"Error loading Freebuff messages: {e}")

    def resume(self, cid: str, workdir: str) -> None:
        if os.path.exists(workdir):
            os.chdir(workdir)
        os.execvp("freebuff", ["freebuff", "--continue", cid])

    def extract_briefing_context(
        self, cid: str, workdir: str
    ) -> Tuple[str, str, List[str], List[str]]:
        title = f"FREEBUFF Session {cid}"
        user_prompts: List[str] = []
        assistant_msgs: List[str] = []

        matches = glob.glob(os.path.join(FREEBUFF_DIR, "*", "chats", cid, "chat-messages.json"))
        if matches:
            chat_dir = os.path.dirname(matches[0])
            meta_path = os.path.join(chat_dir, "chat-meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as mf:
                        m_data = json.load(mf)
                        fp = clean_text(m_data.get("firstPrompt", ""))
                        if fp:
                            title = fp[:60]
                except Exception:
                    pass

            run_state_path = os.path.join(chat_dir, "run-state.json")
            if os.path.exists(run_state_path):
                try:
                    with open(run_state_path, "r", encoding="utf-8") as rf:
                        rs = json.load(rf)
                        fc = rs.get("sessionState", {}).get("fileContext", {})
                        real_root = fc.get("projectRoot") or fc.get("cwd")
                        if real_root and os.path.exists(real_root):
                            workdir = real_root
                except Exception:
                    pass

            try:
                with open(matches[0], "r", encoding="utf-8") as f:
                    msgs = json.load(f)
                    for m in msgs:
                        v = m.get("variant", "")
                        c = m.get("content", "")
                        if not c:
                            for b in m.get("blocks", []):
                                if b.get("type") == "text" and b.get("textType") != "reasoning":
                                    c = b.get("content") or b.get("text") or ""
                        txt = clean_text(c)
                        if txt:
                            if v == "user":
                                user_prompts.append(txt)
                            elif v == "ai":
                                assistant_msgs.append(txt)
            except Exception:
                pass

        return title, workdir, user_prompts, assistant_msgs

    def receive_handoff(self, briefing: str, title: str, workdir: str) -> None:
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        chat_id = now_dt.strftime("%Y-%m-%dT%H-%M-%S.000Z")
        proj_name = os.path.basename(os.path.abspath(workdir))
        chat_dir = os.path.expanduser(f"~/.config/manicode/projects/{proj_name}/chats/{chat_id}")
        os.makedirs(chat_dir, exist_ok=True)

        now_ms = int(time.time() * 1000)
        now_str = datetime.datetime.now().strftime("%I:%M %p")

        messages = [
            {
                "id": f"divider-{now_ms}",
                "variant": "ai",
                "content": "",
                "blocks": [{"type": "mode-divider", "mode": "LITE"}],
                "timestamp": now_str,
            },
            {
                "id": f"user-{now_ms+1}",
                "variant": "user",
                "content": briefing,
                "timestamp": now_str,
            },
        ]
        msgs_path = os.path.join(chat_dir, "chat-messages.json")
        msgs_json = json.dumps(messages, indent=2)
        with open(msgs_path, "w", encoding="utf-8") as f:
            f.write(msgs_json)

        st = os.stat(msgs_path)
        meta = {
            "messageCount": len(messages),
            "firstPrompt": title[:100],
            "messagesSize": st.st_size,
            "messagesMtimeMs": int(st.st_mtime * 1000),
        }
        with open(os.path.join(chat_dir, "chat-meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        run_state = {
            "sessionState": {
                "fileContext": {
                    "projectRoot": workdir,
                    "cwd": workdir,
                }
            }
        }
        with open(os.path.join(chat_dir, "run-state.json"), "w", encoding="utf-8") as f:
            json.dump(run_state, f, indent=2)

        # Seed message-history.json so user can press Up Arrow
        msg_hist_path = os.path.expanduser("~/.config/manicode/message-history.json")
        try:
            hist = []
            if os.path.exists(msg_hist_path):
                with open(msg_hist_path, "r", encoding="utf-8") as f:
                    hist = json.load(f)
            action_prompt = "Review HANDOFF.md and proceed with the objective."
            if action_prompt in hist:
                hist.remove(action_prompt)
            hist.append(action_prompt)
            with open(msg_hist_path, "w", encoding="utf-8") as f:
                json.dump(hist, f, indent=2)
        except Exception:
            pass

        print(f"\033[32m✓ Initialized Freebuff handoff session: {chat_id}\033[0m")
        print(f"\033[32m✓ Seeded prompt in Freebuff history (press Up Arrow inside Freebuff to submit)\033[0m")
        time.sleep(1.2)

        if os.path.exists(workdir):
            os.chdir(workdir)

        os.execvp("freebuff", ["freebuff", "--continue", chat_id])
