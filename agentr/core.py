"""
agentr.core: Data structures, text sanitization, clipboard handling,
             and cross-agent handoff briefing construction.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional, List, Tuple

AGENT_TAGS = {
    "agy": "\033[1;35m[agy]\033[0m",
    "opencode": "\033[1;36m[opencode]\033[0m",
    "freebuff": "\033[1;33m[freebuff]\033[0m",
    "grok": "\033[1;32m[grok]\033[0m",
    "kimi": "\033[1;34m[kimi]\033[0m",
    "claude": "\033[1;31m[claude]\033[0m",
    "codex": "\033[1;34m[codex]\033[0m",
}


@dataclass
class SessionInfo:
    timestamp: float
    agent: str
    cid: str
    dt_str: str
    title: str
    step_count: int
    snippet: str
    workdir: str

    @property
    def key(self) -> str:
        return f"{self.agent}:{self.cid}:{self.workdir}"

    def to_fzf_line(self) -> str:
        tag = AGENT_TAGS.get(self.agent, f"[{self.agent}]")
        step_str = f"({self.step_count:2d} turns)" if self.step_count > 0 else "        "
        title_fmt = self.title[:32]
        return f"{self.key}\t{tag:<20} \033[36m{self.dt_str}\033[0m  │  \033[1m{title_fmt:<32}\033[0m  \033[34m{step_str}\033[0m  \033[90m│ {self.snippet}\033[0m"


@dataclass
class SearchResult:
    timestamp: float
    agent: str
    cid: str
    workdir: str
    dt_str: str
    title: str
    step_count: int
    snippet: str

    @property
    def key(self) -> str:
        return f"{self.agent}:{self.cid}:{self.workdir}"

    def to_fzf_line(self) -> str:
        tag = AGENT_TAGS.get(self.agent, f"[{self.agent}]")
        step_str = f"({self.step_count:2d} turns)" if self.step_count > 0 else "        "
        title_fmt = (self.title or "(Untitled)")[:32]
        return f"{self.key}\t{tag:<20} \033[36m{self.dt_str}\033[0m  │  \033[1m{title_fmt:<32}\033[0m  \033[34m{step_str}\033[0m  \033[33m│ {self.snippet}\033[0m"


def clean_text(s: Optional[str]) -> str:
    """Strip XML wrappers, system tags, and normalise whitespace."""
    if not s:
        return ""
    s = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", s, flags=re.DOTALL)
    s = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", s, flags=re.DOTALL)
    s = re.sub(r"</?[A-Z_]+>", "", s)
    return " ".join(s.split())


def highlight_matches(text: str, query: Optional[str], fg_color: str = "37") -> str:
    """Highlight query substrings using ANSI colors."""
    if not query or len(query.strip()) < 2:
        return text
    tokens = re.split(f"({re.escape(query)})", text, flags=re.IGNORECASE)
    res = []
    for t in tokens:
        if t.lower() == query.lower():
            res.append(f"\033[1;93;44m{t}\033[0;{fg_color}m")
        else:
            res.append(t)
    return "".join(res)


def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard with fallback through Wayland and X11 tools."""
    for cmd in [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]:
        try:
            res = subprocess.run(
                cmd,
                input=text,
                text=True,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if res.returncode == 0:
                return True
        except Exception:
            continue
    return False


def build_handoff_briefing(
    source_agent: str,
    cid: str,
    workdir: str,
    title: str,
    user_prompts: List[str],
    assistant_msgs: List[str],
) -> Tuple[str, str, str]:
    """Construct a clean, zero-loss markdown handoff briefing from session state."""
    # Filter out bare slash commands like /model, /plan when determining pending instruction
    meaningful_prompts = [
        p for p in user_prompts
        if not (p.startswith("/") and len(p.split()) <= 1)
    ]
    if not meaningful_prompts:
        meaningful_prompts = user_prompts

    first_prompt = meaningful_prompts[0] if meaningful_prompts else "(No initial prompt recorded)"
    last_prompt = meaningful_prompts[-1] if meaningful_prompts else "(No pending prompt recorded)"

    recent_summary = ""
    for a in reversed(assistant_msgs):
        if len(a.strip()) > 50:
            recent_summary = a.strip()
            break
    if not recent_summary:
        for a in reversed(assistant_msgs):
            if a.strip():
                recent_summary = a.strip()
                break
    if len(recent_summary) > 650:
        recent_summary = recent_summary[:647] + "..."

    # Check for relevant reports/files in working directory
    reports_info = ""
    candidates = [os.path.join(workdir, "reports")]
    if any(k in title.lower() or k in first_prompt.lower() for k in ["rescue", "hdd", "chkdsk", "disk", "repair"]):
        candidates.append(os.path.join(workdir, "DataRescue", "reports"))

    for r_dir in candidates:
        if os.path.exists(r_dir):
            files = [f for f in os.listdir(r_dir) if f.endswith(".md") or f.endswith(".csv")]
            if files:
                reports_info = f"Relevant reports available in {r_dir}: {', '.join(files[:6])}"
                break

    # Check for CAD designs or parametric source files (SolidCraft)
    cad_info = ""
    if os.path.exists(workdir):
        cad_exts = (".sc", ".solidcraft", ".step", ".stl")
        found_cad = []
        for root, dirs, files in os.walk(workdir):
            # Do not traverse git or hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            rel_depth = os.path.relpath(root, workdir).count(os.sep)
            if rel_depth > 2:
                dirs[:] = []
            for f in files:
                if any(f.endswith(ext) for ext in cad_exts):
                    rel = os.path.relpath(os.path.join(root, f), workdir)
                    found_cad.append(rel)
                    if len(found_cad) >= 8:
                        break
            if len(found_cad) >= 8:
                break
        if found_cad:
            cad_info = f"CAD Models / Exports in {workdir}: {', '.join(found_cad[:6])}"

    briefing = f"""You are picking up an ongoing session transferred from {source_agent.upper()}.

=== SESSION HANDOFF BRIEFING ===
• Source Agent: {source_agent.upper()} (Session ID: {cid})
• Original Goal: {title}
• Working Directory: {workdir}
• Initial Prompt: {first_prompt}
"""
    if reports_info:
        briefing += f"• Files/Reports: {reports_info}\n"
    if cad_info:
        briefing += f"• CAD State: {cad_info}\n"

    briefing += f"""
=== LAST COMPLETED STATUS (FROM {source_agent.upper()}) ===
{recent_summary or "(No summary recorded)"}

=== USER'S CURRENT OBJECTIVE / PENDING INSTRUCTION ===
{last_prompt}
================================

Please review this handoff context, check the local files, and immediately proceed with the user's objective above."""

    return briefing, title, workdir
