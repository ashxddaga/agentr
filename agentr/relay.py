"""
agentr.relay: Token exhaustion detection, free-tier cascading,
              and automatic session relay between coding agents.
"""
from __future__ import annotations

import os
import re
import sys
import subprocess
from typing import Optional, List, Tuple

from .core import SessionInfo, build_handoff_briefing, copy_to_clipboard
from .adapters import get_adapter, get_active_adapters

# Comprehensive patterns detecting rate limits, credit exhaustion, and quota errors
RATE_LIMIT_PATTERNS = [
    r"(?i)\b429\b",
    r"(?i)too many requests",
    r"(?i)rate[\s_-]?limit",
    r"(?i)quota[\s_-]?exceeded",
    r"(?i)resource_exhausted",
    r"(?i)insufficient[\s_-]?quota",
    r"(?i)out of credits",
    r"(?i)(credit|usage|daily|hourly|monthly|token|free|current)[\s_-]?limit",
    r"(?i)reached.*limit",
    r"(?i)limit.*reached",
    r"(?i)tokens? (per minute|per day|limit) exceeded",
    r"(?i)plan allowance exhausted",
    r"(?i)overloaded_error",
]

DEFAULT_CASCADE = ["agy", "opencode", "freebuff", "claude"]


def is_rate_limit_error(text: str) -> bool:
    """Return True if the text contains known quota or rate limit indicators."""
    if not text:
        return False
    for pat in RATE_LIMIT_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def get_cascade_target(
    current_agent: str,
    custom_cascade: Optional[List[str]] = None,
) -> Optional[str]:
    """Determine the next fallback agent in the cascade chain."""
    chain = custom_cascade if custom_cascade else DEFAULT_CASCADE
    # Filter to available active adapters
    active_names = [a.name for a in get_active_adapters()]
    valid_chain = [agent for agent in chain if agent in active_names]

    if not valid_chain:
        return None

    if current_agent in valid_chain:
        curr_idx = valid_chain.index(current_agent)
        # Next agent in cyclical chain
        next_idx = (curr_idx + 1) % len(valid_chain)
        return valid_chain[next_idx]
    else:
        return valid_chain[0]


def find_latest_session(
    workdir: Optional[str] = None,
    agent: Optional[str] = None,
) -> Optional[SessionInfo]:
    """Find the most recent session, prioritizing current working directory."""
    adapters = [get_adapter(agent)] if agent and get_adapter(agent) else get_active_adapters()
    candidates: List[SessionInfo] = []

    norm_workdir = os.path.realpath(workdir) if workdir else None

    for a in adapters:
        if a:
            try:
                candidates.extend(a.list_sessions())
            except Exception:
                pass

    if norm_workdir:
        # Match sessions in the same working directory first
        dir_candidates = [
            s for s in candidates
            if s.workdir and os.path.realpath(s.workdir) == norm_workdir
        ]
        if dir_candidates:
            dir_candidates.sort(key=lambda s: s.timestamp, reverse=True)
            return dir_candidates[0]

    if candidates:
        candidates.sort(key=lambda s: s.timestamp, reverse=True)
        return candidates[0]

    return None


def execute_relay(
    source_target: Optional[str] = None,
    target_agent: Optional[str] = None,
    workdir: Optional[str] = None,
    custom_cascade: Optional[List[str]] = None,
    auto_confirm: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Relay the latest session (or specified session) to the next cascade agent.
    Returns True if successfully launched or planned (if dry_run).
    """
    session: Optional[SessionInfo] = None

    if source_target:
        # Check if source_target is agent:cid:workdir
        if ":" in source_target:
            parts = source_target.split(":")
            src_agent, cid = parts[0], parts[1]
            src_workdir = ":".join(parts[2:]) if len(parts) > 2 else (workdir or os.getcwd())
            adapter = get_adapter(src_agent)
            if adapter:
                session = SessionInfo(
                    timestamp=0.0,
                    agent=src_agent,
                    cid=cid,
                    title="Targeted Session",
                    workdir=src_workdir,
                )
        else:
            # Look up session by CID prefix
            for a in get_active_adapters():
                for s in a.list_sessions():
                    if s.cid == source_target or s.cid.startswith(source_target):
                        session = s
                        break
                if session:
                    break

    if not session:
        active_dir = workdir or os.getcwd()
        session = find_latest_session(workdir=active_dir)

    if not session:
        print("\033[31mError: No active or recent agent session found to relay.\033[0m", file=sys.stderr)
        return False

    source_adapter = get_adapter(session.agent)
    if not source_adapter:
        print(f"\033[31mError: Unknown source adapter '{session.agent}'.\033[0m", file=sys.stderr)
        return False

    # Determine target agent
    if not target_agent:
        target_agent = get_cascade_target(session.agent, custom_cascade)

    if not target_agent or target_agent == session.agent:
        # If fallback chain only has the current agent, pick any other active adapter
        active_others = [a.name for a in get_active_adapters() if a.name != session.agent]
        if active_others:
            target_agent = active_others[0]
        else:
            print("\033[31mError: No alternative agent available for relay.\033[0m", file=sys.stderr)
            return False

    target_adapter = get_adapter(target_agent)
    if not target_adapter:
        print(f"\033[31mError: Unknown target adapter '{target_agent}'.\033[0m", file=sys.stderr)
        return False

    # Extract context and build handoff briefing
    title, session_workdir, user_prompts, assistant_msgs = source_adapter.extract_briefing_context(
        session.cid, session.workdir
    )
    briefing, title, final_workdir = build_handoff_briefing(
        session.agent, session.cid, session_workdir, title, user_prompts, assistant_msgs
    )

    print("\n\033[1;36m═══════════════════════════════════════════════════════════════\033[0m")
    print(f"\033[1;33m⚡ AGENTR TOKEN RELAY / FREE-TIER CASCADE\033[0m")
    print(f"  Source: \033[1m{source_adapter.display_name}\033[0m (Session \033[36m{session.cid[:12]}\033[0m)")
    print(f"  Target: \033[1m{target_adapter.display_name}\033[0m")
    print(f"  Task:   \033[33m{title}\033[0m")
    print(f"  Dir:    \033[34m{final_workdir}\033[0m")
    print("\033[1;36m═══════════════════════════════════════════════════════════════\033[0m\n")

    if dry_run:
        print("\033[1;32m[DRY RUN] Generated Handoff Briefing:\033[0m")
        print("───────────────────────────────────────────────────────────────")
        print(briefing[:500] + ("\n..." if len(briefing) > 500 else ""))
        print("───────────────────────────────────────────────────────────────")
        print(f"\033[32m✓ Dry-run completed. Target: {target_adapter.display_name} in {final_workdir}\033[0m")
        return True

    if not auto_confirm:
        try:
            choice = input(f"Launch {target_adapter.display_name} with handoff briefing? [Y/n]: ").strip().lower()
            if choice in ("n", "no"):
                print("Relay cancelled.")
                return False
        except (EOFError, KeyboardInterrupt):
            print("\nRelay cancelled.")
            return False

    # Save handoff briefing to file
    handoff_file = os.path.join(final_workdir, "HANDOFF.md")
    try:
        with open(handoff_file, "w", encoding="utf-8") as f:
            f.write(briefing)
        print(f"\033[32m✓ Handoff briefing saved to {handoff_file}\033[0m")
    except Exception:
        fallback_file = f"/tmp/handoff_{session.agent}_{session.cid[:8]}.md"
        with open(fallback_file, "w", encoding="utf-8") as f:
            f.write(briefing)
        print(f"\033[32m✓ Handoff briefing saved to {fallback_file}\033[0m")

    # Copy to clipboard
    if copy_to_clipboard(briefing):
        print("\033[32m✓ Briefing copied to clipboard\033[0m")

    print(f"\nBooting \033[1m{target_adapter.display_name}\033[0m...\n")
    target_adapter.receive_handoff(briefing, title, final_workdir)
    return True
