"""
agentr.live_relay: Real-time workspace context extraction, snapshot serialization,
                   and zero-loss cross-agent broadcast relay for active debugging
                   and CAD problem-solving fleets.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import time
from typing import Dict, Any, List, Optional, Tuple

from .core import copy_to_clipboard
from .adapters import get_adapter, get_active_adapters
from .cad import parse_stl, find_solidcraft_cli

SNAPSHOT_DIR = ".agentr"
SNAPSHOT_FILENAME = "live_context.json"
BRIEFING_FILENAME = "live_briefing.md"

CAD_EXTENSIONS = (
    ".solidcraft",
    ".sc",
    ".step",
    ".stp",
    ".stl",
    ".dxf",
    ".brep",
    ".fcstd",
    ".iges",
    ".igs",
)

# Common error signatures in logs, compiler output, test failures, and LLM rate limit crashes
ERROR_SIGNATURES = [
    r"(?i)error[E\d+]",
    r"(?i)panicked at",
    r"(?i)\bfailed\b",
    r"(?i)\bfailure\b",
    r"(?i)traceback \(most recent call last\)",
    r"(?i)assertionerror",
    r"(?i)sigsegv",
    r"(?i)supergrok",
    r"(?i)grok[\s_-]?build[\s_-]?usage[\s_-]?limit",
    r"(?i)usage limit for now",
    r"(?i)too many requests",
    r"(?i)rate[\s_-]?limit",
    r"(?i)quota[\s_-]?exceeded",
    r"(?i)resource_exhausted",
    r"(?i)insufficient[\s_-]?quota",
    r"(?i)out of credits",
]


def extract_git_context(workdir: str) -> Dict[str, Any]:
    """Extract live git branch, status, ahead/behind, diff stats, and diff patch."""
    git_info: Dict[str, Any] = {
        "is_repo": False,
        "branch": "",
        "status": "",
        "ahead_behind": "",
        "diff_stat": "",
        "diff_patch": "",
        "uncommitted_files": [],
        "has_uncommitted_changes": False,
    }
    if not os.path.isdir(workdir):
        return git_info

    try:
        r = subprocess.run(
            ["git", "-C", workdir, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return git_info
        git_info["is_repo"] = True
    except Exception:
        return git_info

    # Branch
    try:
        r = subprocess.run(
            ["git", "-C", workdir, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_info["branch"] = r.stdout.strip()
    except Exception:
        pass

    # Status short
    try:
        r = subprocess.run(
            ["git", "-C", workdir, "status", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        status_out = r.stdout.strip()
        git_info["status"] = status_out
        if status_out:
            files = []
            for line in status_out.splitlines():
                parts = line.strip().split(maxsplit=1)
                f = parts[1] if len(parts) == 2 else parts[0]
                if f.startswith(".agentr") or f in ("HANDOFF.md", ".agentr/"):
                    continue
                files.append(f)
            git_info["uncommitted_files"] = files
            git_info["has_uncommitted_changes"] = bool(files)
    except Exception:
        pass

    # Ahead / Behind
    try:
        r = subprocess.run(
            ["git", "-C", workdir, "status", "-sb"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = r.stdout.splitlines()[0] if r.stdout.splitlines() else ""
        if "[" in first_line and "]" in first_line:
            git_info["ahead_behind"] = first_line[first_line.find("[") : first_line.find("]") + 1]
    except Exception:
        pass

    # Diff stat against HEAD
    try:
        r = subprocess.run(
            ["git", "-C", workdir, "diff", "HEAD", "--stat"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            git_info["diff_stat"] = r.stdout.strip()
        else:
            r2 = subprocess.run(
                ["git", "-C", workdir, "diff", "--stat"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            git_info["diff_stat"] = r2.stdout.strip()
    except Exception:
        pass

    # Diff patch (truncated to avoid blowing LLM context windows)
    try:
        r = subprocess.run(
            ["git", "-C", workdir, "diff", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        patch = r.stdout if r.returncode == 0 else ""
        if not patch:
            r2 = subprocess.run(
                ["git", "-C", workdir, "diff"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            patch = r2.stdout

        lines = patch.splitlines()
        if len(lines) > 250:
            patch = "\n".join(lines[:250]) + f"\n... [diff truncated: {len(lines) - 250} lines omitted]"
        elif len(patch) > 12000:
            patch = patch[:12000] + "\n... [diff truncated for length]"
        git_info["diff_patch"] = patch.strip()
    except Exception:
        pass

    return git_info


def extract_error_logs(
    workdir: str,
    custom_errors: Optional[List[str]] = None,
    max_errors: int = 5,
) -> List[Dict[str, Any]]:
    """Scan workspace for recent error files, failure logs, and crash outputs."""
    errors: List[Dict[str, Any]] = []

    # 1. Add any custom errors passed via telemetry or parameter
    if custom_errors:
        for err in custom_errors:
            if not err or not err.strip():
                continue
            err_clean = err.strip()
            etype = "RateLimitExhaustion" if any(re.search(p, err_clean) for p in [r"(?i)usage limit", r"(?i)429", r"(?i)quota", r"(?i)supergrok"]) else "ExecutionFailure"
            errors.append({
                "source": "telemetry",
                "error_type": etype,
                "snippet": err_clean[:3000],
                "mtime": time.time(),
            })

    # 2. Check for log files in workdir (.agentr, root, target, build)
    candidate_dirs = [
        os.path.join(workdir, SNAPSHOT_DIR),
        workdir,
        os.path.join(workdir, "target"),
        os.path.join(workdir, "logs"),
        "/tmp",
    ]

    log_files: List[Tuple[float, str]] = []
    for d in candidate_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.scandir(d):
                if entry.is_file() and (entry.name.endswith(".log") or entry.name.endswith(".err") or "error" in entry.name.lower()):
                    try:
                        mtime = entry.stat().st_mtime
                        # Only examine files modified within the last 24 hours
                        if time.time() - mtime < 86400:
                            log_files.append((mtime, entry.path))
                    except Exception:
                        pass
        except Exception:
            pass

    log_files.sort(key=lambda x: x[0], reverse=True)

    for mtime, fpath in log_files[:10]:
        if len(errors) >= max_errors:
            break
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if not content.strip():
                continue

            has_err = False
            for pat in ERROR_SIGNATURES:
                if re.search(pat, content):
                    has_err = True
                    break

            if has_err:
                lines = content.strip().splitlines()
                # Extract the last 40 lines of the failure log
                snippet = "\n".join(lines[-40:])
                rel_path = os.path.relpath(fpath, workdir) if fpath.startswith(workdir) else fpath
                errors.append({
                    "source": rel_path,
                    "error_type": "LogFileError",
                    "snippet": snippet[:3000],
                    "mtime": mtime,
                })
        except Exception:
            pass

    return errors[:max_errors]


def extract_cad_context(workdir: str, max_files: int = 25) -> Dict[str, Any]:
    """Scan workspace for CAD files, compute mesh metrics (watertight, triangles), and check SolidCraft status."""
    cad_files: List[Dict[str, Any]] = []
    solidcraft_cli = find_solidcraft_cli()

    ignore_dirs = {
        ".git", "node_modules", "target", ".cargo", "vendor",
        ".gemini", "dist", "build", ".venv", "venv", "__pycache__",
    }

    if os.path.isdir(workdir):
        for root, dirs, files in os.walk(workdir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            # Restrict depth to 5
            rel_root = os.path.relpath(root, workdir)
            if rel_root != "." and rel_root.count(os.sep) >= 5:
                dirs[:] = []
                continue

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in CAD_EXTENSIONS:
                    full_p = os.path.join(root, f)
                    try:
                        st = os.stat(full_p)
                        item: Dict[str, Any] = {
                            "path": os.path.relpath(full_p, workdir),
                            "ext": ext,
                            "size_bytes": st.st_size,
                            "mtime": st.st_mtime,
                        }
                        if ext == ".stl":
                            try:
                                parsed = parse_stl(full_p)
                                if "error" not in parsed:
                                    item["watertight"] = parsed.get("watertight", False)
                                    item["triangles"] = parsed.get("triangles", 0)
                                    item["volume_mm3"] = parsed.get("volume_mm3", 0.0)
                            except Exception:
                                pass
                        cad_files.append(item)
                        if len(cad_files) >= max_files:
                            break
                    except Exception:
                        pass
            if len(cad_files) >= max_files:
                break

    # Build concise human summary
    summary_parts = []
    if cad_files:
        ext_counts: Dict[str, int] = {}
        stl_watertight = 0
        stl_total = 0
        for c in cad_files:
            e = c["ext"]
            ext_counts[e] = ext_counts.get(e, 0) + 1
            if e == ".stl":
                stl_total += 1
                if c.get("watertight"):
                    stl_watertight += 1

        counts_str = ", ".join(f"{cnt} {ext}" for ext, cnt in ext_counts.items())
        stl_info = f", STLs: {stl_watertight}/{stl_total} watertight" if stl_total > 0 else ""
        summary_parts.append(f"{len(cad_files)} CAD files ({counts_str}{stl_info})")
    else:
        summary_parts.append("No local CAD models detected")

    if solidcraft_cli:
        summary_parts.append("SolidCraft CLI active")

    return {
        "solidcraft_available": bool(solidcraft_cli),
        "solidcraft_cli": solidcraft_cli,
        "file_count": len(cad_files),
        "files": cad_files,
        "summary": " • ".join(summary_parts),
    }


def extract_session_context(workdir: str) -> Optional[Dict[str, Any]]:
    """Locate the most recent active agent session in workdir for continuous context."""
    from .relay import find_latest_session
    latest = find_latest_session(workdir=workdir)
    if not latest:
        return None

    adapter = get_adapter(latest.agent)
    title = latest.title
    last_prompt = ""
    last_assistant = ""

    if adapter:
        try:
            t, w, prompts, msgs = adapter.extract_briefing_context(latest.cid, latest.workdir)
            if t:
                title = t
            if prompts:
                last_prompt = prompts[-1]
            if msgs:
                last_assistant = msgs[-1]
        except Exception:
            pass

    return {
        "agent": latest.agent,
        "cid": latest.cid,
        "title": title,
        "workdir": latest.workdir,
        "last_user_prompt": last_prompt[:1500] if last_prompt else "",
        "last_assistant_msg": last_assistant[:1500] if last_assistant else "",
    }


def capture_live_snapshot(
    workdir: Optional[str] = None,
    save: bool = True,
    custom_errors: Optional[List[str]] = None,
    task_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract full real-time workspace snapshot (git, errors, CAD, session)
    and serialize to .agentr/live_context.json.
    """
    target_workdir = os.path.abspath(workdir or os.getcwd())
    git_info = extract_git_context(target_workdir)
    error_info = extract_error_logs(target_workdir, custom_errors=custom_errors)
    cad_info = extract_cad_context(target_workdir)
    session_info = extract_session_context(target_workdir)

    now = time.time()
    iso_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

    snapshot: Dict[str, Any] = {
        "version": "1.0",
        "timestamp": now,
        "iso_time": iso_time,
        "workdir": target_workdir,
        "task_title": task_title or (session_info.get("title") if session_info else "") or "Live Task",
        "git": git_info,
        "errors": error_info,
        "cad": cad_info,
        "session": session_info,
    }

    if save:
        agentr_dir = os.path.join(target_workdir, SNAPSHOT_DIR)
        os.makedirs(agentr_dir, exist_ok=True)
        snapshot_path = os.path.join(agentr_dir, SNAPSHOT_FILENAME)
        try:
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to write {snapshot_path}: {e}", file=sys.stderr)

    return snapshot


def load_live_snapshot(workdir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load cached snapshot from .agentr/live_context.json if available."""
    target_workdir = os.path.abspath(workdir or os.getcwd())
    snapshot_path = os.path.join(target_workdir, SNAPSHOT_DIR, SNAPSHOT_FILENAME)
    if not os.path.isfile(snapshot_path):
        return None
    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def format_live_briefing(snapshot: Dict[str, Any], prompt: Optional[str] = None) -> str:
    """Format live workspace snapshot into an actionable briefing for peer agents."""
    workdir = snapshot.get("workdir", "")
    git = snapshot.get("git", {})
    cad = snapshot.get("cad", {})
    errors = snapshot.get("errors", [])
    session = snapshot.get("session") or {}
    task_goal = prompt or snapshot.get("task_title") or "Collaborate on active debugging and verification"

    branch_str = git.get("branch") or "detached/unknown"
    if git.get("ahead_behind"):
        branch_str += f" {git.get('ahead_behind')}"

    diff_stat = git.get("diff_stat") or "(No uncommitted diff stats)"
    diff_patch = git.get("diff_patch") or ""
    cad_summary = cad.get("summary") or "No CAD files"

    lines = [
        "You are collaborating on an active workspace session transferred via AgentR Live Relay.",
        "",
        "=== LIVE WORKSPACE CONTEXT ===",
        f"• Workspace Directory: {workdir}",
        f"• Git Branch:          {branch_str}",
        f"• Working Tree State:  {'DIRTY (Uncommitted changes)' if git.get('has_uncommitted_changes') else 'CLEAN'}",
        f"• CAD Environment:     {cad_summary}",
        f"• Active Errors Found: {len(errors)}",
        "",
        "=== OBJECTIVE / PENDING TASK ===",
        f"{task_goal}",
        "",
    ]

    if errors:
        lines.append("=== ACTIVE FAILURES & ERROR TRACES ===")
        for i, err in enumerate(errors, 1):
            lines.append(f"[{i}] Source: {err.get('source')} ({err.get('error_type')})")
            lines.append("```")
            lines.append(err.get("snippet", "").strip())
            lines.append("```")
            lines.append("")

    if diff_stat.strip():
        lines.append("=== UNCOMMITTED CHANGES (DIFF STAT) ===")
        lines.append(diff_stat)
        lines.append("")

    if diff_patch.strip():
        lines.append("=== UNCOMMITTED CHANGES (PATCH PREVIEW) ===")
        lines.append("```diff")
        lines.append(diff_patch)
        lines.append("```")
        lines.append("")

    cad_files = cad.get("files", [])
    if cad_files:
        lines.append("=== CAD FILE INVENTORY ===")
        for c in cad_files[:10]:
            p = c.get("path")
            sz = c.get("size_bytes", 0)
            extra = []
            if "watertight" in c:
                extra.append(f"watertight: {c.get('watertight')}")
            if "triangles" in c:
                extra.append(f"{c.get('triangles')} triangles")
            if "volume_mm3" in c:
                extra.append(f"vol: {c.get('volume_mm3')} mm³")
            extra_str = f" ({', '.join(extra)})" if extra else ""
            lines.append(f"• {p} [{sz} bytes]{extra_str}")
        lines.append("")

    if session:
        lines.append("=== PREVIOUS SESSION CONTEXT ===")
        lines.append(f"• Source Agent: {session.get('agent', '').upper()} (ID: {session.get('cid', '')[:16]})")
        lines.append(f"• Session Title: {session.get('title')}")
        if session.get("last_user_prompt"):
            lines.append(f"• Last User Prompt: {session.get('last_user_prompt')[:300]}")
        if session.get("last_assistant_msg"):
            lines.append(f"• Last Output: {session.get('last_assistant_msg')[:400]}")
        lines.append("")

    lines.append("===============================================================")
    lines.append("Please inspect the local workspace files, address any active errors, and proceed with the objective above.")

    return "\n".join(lines)


def format_live_summary(snapshot: Dict[str, Any]) -> str:
    """Format snapshot for terminal display with ANSI colors."""
    workdir = snapshot.get("workdir", "")
    git = snapshot.get("git", {})
    cad = snapshot.get("cad", {})
    errors = snapshot.get("errors", [])
    session = snapshot.get("session") or {}

    out = []
    out.append("\033[1;36m═══════════════════════════════════════════════════════════════\033[0m")
    out.append("\033[1;33m⚡ AGENTR LIVE WORKSPACE SNAPSHOT\033[0m")
    out.append(f"  Directory: \033[34m{workdir}\033[0m")
    if git.get("is_repo"):
        branch_line = f"  Git:       \033[1m{git.get('branch')}\033[0m"
        if git.get("ahead_behind"):
            branch_line += f" \033[33m{git.get('ahead_behind')}\033[0m"
        if git.get("has_uncommitted_changes"):
            branch_line += f" \033[31m({len(git.get('uncommitted_files', []))} uncommitted files)\033[0m"
        else:
            branch_line += " \033[32m(clean)\033[0m"
        out.append(branch_line)

    out.append(f"  CAD State: \033[35m{cad.get('summary', 'None')}\033[0m")

    if errors:
        out.append(f"  Errors:    \033[1;31m{len(errors)} active failure(s) detected\033[0m")
        for err in errors[:3]:
            snippet_first = err.get("snippet", "").splitlines()[0] if err.get("snippet") else ""
            out.append(f"             • [{err.get('source')}]: \033[90m{snippet_first[:60]}\033[0m")
    else:
        out.append("  Errors:    \033[32mNone detected\033[0m")

    if session:
        out.append(f"  Session:   \033[36m{session.get('agent', '').upper()}\033[0m ({session.get('cid', '')[:12]}) - {session.get('title')}")

    out.append(f"  Snapshot:  \033[90m{os.path.join(workdir, SNAPSHOT_DIR, SNAPSHOT_FILENAME)}\033[0m")
    out.append("\033[1;36m═══════════════════════════════════════════════════════════════\033[0m")
    return "\n".join(out)


def broadcast_live_context(
    target_agent: str,
    workdir: Optional[str] = None,
    prompt: Optional[str] = None,
    dry_run: bool = False,
    non_interactive: bool = False,
    custom_errors: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """
    Capture live workspace snapshot and broadcast it to target agent with zero context loss.
    """
    target_name = target_agent.lower().strip()
    adapter = get_adapter(target_name)
    if not adapter:
        print(f"\033[31mError: Unknown target agent '{target_agent}'.\033[0m", file=sys.stderr)
        valid = [a.name for a in get_active_adapters()]
        print(f"Available agents: {', '.join(valid)}", file=sys.stderr)
        return False, ""

    target_workdir = os.path.abspath(workdir or os.getcwd())
    snapshot = capture_live_snapshot(
        target_workdir,
        save=True,
        custom_errors=custom_errors,
        task_title=prompt,
    )
    briefing = format_live_briefing(snapshot, prompt=prompt)

    # Save live briefing files
    briefing_path = os.path.join(target_workdir, SNAPSHOT_DIR, BRIEFING_FILENAME)
    handoff_path = os.path.join(target_workdir, "HANDOFF.md")
    try:
        with open(briefing_path, "w", encoding="utf-8") as f:
            f.write(briefing)
        with open(handoff_path, "w", encoding="utf-8") as f:
            f.write(briefing)
    except Exception:
        pass

    copy_to_clipboard(briefing)

    task_title = prompt or snapshot.get("task_title") or "Live Context Collaboration"
    print("\n\033[1;36m═══════════════════════════════════════════════════════════════\033[0m")
    print(f"\033[1;33m⚡ AGENTR LIVE CONTEXT BROADCAST\033[0m")
    print(f"  Target:    \033[1;32m{adapter.display_name}\033[0m")
    print(f"  Workspace: \033[34m{target_workdir}\033[0m")
    print(f"  Task:      \033[33m{task_title}\033[0m")
    if snapshot.get("git", {}).get("is_repo"):
        print(f"  Branch:    \033[1m{snapshot['git'].get('branch')}\033[0m")
    print("\033[1;36m═══════════════════════════════════════════════════════════════\033[0m\n")

    if dry_run:
        print("\033[1;32m[DRY RUN] Generated Live Briefing Preview:\033[0m")
        print("───────────────────────────────────────────────────────────────")
        preview_lines = briefing.splitlines()[:25]
        print("\n".join(preview_lines))
        if len(briefing.splitlines()) > 25:
            print("...")
        print("───────────────────────────────────────────────────────────────")
        print(f"\033[32m✓ Dry-run completed. Target: {adapter.display_name} in {target_workdir}\033[0m")
        return True, briefing

    print(f"Launching \033[1m{adapter.display_name}\033[0m with live context briefing...\n")
    try:
        adapter.receive_handoff(
            briefing=briefing,
            title=task_title,
            workdir=target_workdir,
            non_interactive=non_interactive,
        )
    except TypeError:
        # Fallback if adapter receive_handoff does not take non_interactive
        adapter.receive_handoff(
            briefing=briefing,
            title=task_title,
            workdir=target_workdir,
        )

    return True, briefing


def detect_and_relay_live(
    error_text: str,
    workdir: Optional[str] = None,
    current_agent: Optional[str] = None,
    target_agent: Optional[str] = None,
    prompt: Optional[str] = None,
    dry_run: bool = False,
    non_interactive: bool = False,
) -> bool:
    """
    Detect rate limits or agent crashes in error_text, snapshot live context,
    and automatically cascade to the next available agent (e.g. OpenCode or AGY).
    """
    from .relay import is_rate_limit_error, get_cascade_target
    if not is_rate_limit_error(error_text):
        return False

    curr = current_agent or "grok"
    target = target_agent or get_cascade_target(curr)
    if not target or target == curr:
        active = [a.name for a in get_active_adapters() if a.name != curr]
        target = active[0] if active else "opencode"

    print(f"\n\033[1;31m⚡ Rate / Quota Limit Detected for [{curr.upper()}]:\033[0m")
    first_line = error_text.strip().splitlines()[0] if error_text.strip() else ""
    print(f"   \033[90m{first_line[:120]}\033[0m")
    print(f"   \033[1;33mInitiating automatic live context relay to [{target.upper()}]...\033[0m")

    success, _ = broadcast_live_context(
        target_agent=target,
        workdir=workdir,
        prompt=prompt,
        dry_run=dry_run,
        non_interactive=non_interactive,
        custom_errors=[error_text],
    )
    return success


def run_live_cli(args: List[str]) -> None:
    """CLI dispatcher for 'agentr live' / 'agentr relay live' commands."""
    if not args or args[0] in ("-h", "--help", "help"):
        print("Usage: agentr live <command> [OPTIONS]")
        print("\nReal-time workspace context extraction and cross-agent collaboration relay:")
        print("  agentr live snapshot [--dir <dir>]")
        print("      Extract and persist active live context snapshot (.agentr/live_context.json).")
        print("  agentr live broadcast <agent> [--prompt \"<task>\"] [--dir <dir>] [--dry-run]")
        print("      Snapshot workspace and launch target agent with live briefing.")
        print("  agentr live show [--dir <dir>] [--json]")
        print("      Display the active live context snapshot.")
        return

    subcmd = args[0]

    # Handle shortcut: 'agentr live <agent>'
    registered_agents = {a.name for a in get_active_adapters()}
    if subcmd in registered_agents and (len(args) == 1 or not args[1].startswith("snap")):
        target = subcmd
        prompt = None
        workdir = None
        dry_run = False
        non_interactive = False
        i = 1
        while i < len(args):
            if args[i] in ("--prompt", "-p") and i + 1 < len(args):
                prompt = args[i + 1]
                i += 2
            elif args[i] in ("--dir", "-d") and i + 1 < len(args):
                workdir = args[i + 1]
                i += 2
            elif args[i] in ("--dry-run", "-n"):
                dry_run = True
                i += 1
            elif args[i] in ("--headless", "--non-interactive", "--auto"):
                non_interactive = True
                i += 1
            else:
                i += 1
        broadcast_live_context(
            target_agent=target,
            workdir=workdir,
            prompt=prompt,
            dry_run=dry_run,
            non_interactive=non_interactive,
        )
        return

    if subcmd == "snapshot":
        workdir = None
        i = 1
        while i < len(args):
            if args[i] in ("--dir", "-d") and i + 1 < len(args):
                workdir = args[i + 1]
                i += 2
            else:
                i += 1
        snap = capture_live_snapshot(workdir, save=True)
        print(format_live_summary(snap))
        snap_file = os.path.join(snap["workdir"], SNAPSHOT_DIR, SNAPSHOT_FILENAME)
        print(f"\033[32m✓ Live context snapshot written to {snap_file}\033[0m")
        return

    elif subcmd == "broadcast":
        if len(args) < 2:
            print("Usage: agentr live broadcast <target-agent> [--prompt \"<task>\"] [--dir <dir>] [--dry-run]", file=sys.stderr)
            sys.exit(1)
        target = args[1]
        prompt = None
        workdir = None
        dry_run = False
        non_interactive = False
        i = 2
        while i < len(args):
            if args[i] in ("--prompt", "-p") and i + 1 < len(args):
                prompt = args[i + 1]
                i += 2
            elif args[i] in ("--dir", "-d") and i + 1 < len(args):
                workdir = args[i + 1]
                i += 2
            elif args[i] in ("--dry-run", "-n"):
                dry_run = True
                i += 1
            elif args[i] in ("--headless", "--non-interactive", "--auto"):
                non_interactive = True
                i += 1
            else:
                i += 1
        broadcast_live_context(
            target_agent=target,
            workdir=workdir,
            prompt=prompt,
            dry_run=dry_run,
            non_interactive=non_interactive,
        )
        return

    elif subcmd == "show":
        workdir = None
        as_json = False
        i = 1
        while i < len(args):
            if args[i] in ("--dir", "-d") and i + 1 < len(args):
                workdir = args[i + 1]
                i += 2
            elif args[i] in ("--json", "-j"):
                as_json = True
                i += 1
            else:
                i += 1

        snap = load_live_snapshot(workdir)
        if not snap:
            # Generate snapshot on the fly if not yet recorded
            target_workdir = os.path.abspath(workdir or os.getcwd())
            snap = capture_live_snapshot(target_workdir, save=True)

        if as_json:
            print(json.dumps(snap, indent=2))
        else:
            print(format_live_summary(snap))
        return

    else:
        print(f"Unknown live command '{subcmd}'. Run 'agentr live --help' for usage.", file=sys.stderr)
        sys.exit(1)
