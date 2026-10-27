"""
agentr.cli: Command-line interface, interactive fzf fuzzy finder,
            and execution dispatch across coding agents.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional, List

from .core import (
    AGENT_TAGS,
    build_handoff_briefing,
    copy_to_clipboard,
)
from .adapters import (
    get_adapter,
    get_active_adapters,
    get_all_adapters,
)
from .relay import execute_relay


def preview_entry(key: str, query: Optional[str] = None) -> None:
    parts = key.split(":")
    if len(parts) < 2:
        return
    agent, cid = parts[0], parts[1]
    adapter = get_adapter(agent)
    if adapter:
        adapter.preview(cid, query)
    else:
        print(f"Unknown agent: {agent}")


def get_recent_unified_lines(filter_agent: Optional[str] = None) -> List[str]:
    adapters = [get_adapter(filter_agent)] if filter_agent and get_adapter(filter_agent) else get_active_adapters()
    all_sessions = []
    for adapter in adapters:
        if adapter:
            all_sessions.extend(adapter.list_sessions())

    all_sessions.sort(key=lambda s: s.timestamp, reverse=True)
    return [s.to_fzf_line() for s in all_sessions]


def search_all_agents(query: str, filter_agent: Optional[str] = None) -> List[str]:
    if not query or len(query.strip()) < 2:
        return get_recent_unified_lines(filter_agent)

    adapters = [get_adapter(filter_agent)] if filter_agent and get_adapter(filter_agent) else get_active_adapters()
    results = []
    for adapter in adapters:
        if adapter:
            results.extend(adapter.search(query))

    results.sort(key=lambda r: r.timestamp, reverse=True)
    return [r.to_fzf_line() for r in results]


def resolve_session_key(target: str) -> Optional[str]:
    """Resolve a full key, CID, or partial CID to a session key 'agent:cid:workdir'."""
    if not target:
        return None
    if ":" in target and len(target.split(":")) >= 3:
        return target
    target_clean = target.strip()
    for adapter in get_active_adapters():
        for s in adapter.list_sessions():
            if s.cid == target_clean or s.cid.startswith(target_clean) or (len(target_clean) >= 6 and target_clean in s.cid):
                return f"{s.agent}:{s.cid}:{s.workdir}"
    return None


def execute_resume(key: str) -> None:
    parts = key.split(":")
    if len(parts) < 3:
        print(f"Invalid session key: {key}", file=sys.stderr)
        sys.exit(1)

    agent, cid, workdir = parts[0], parts[1], ":".join(parts[2:])
    adapter = get_adapter(agent)
    if not adapter:
        print(f"Unknown agent: {agent}", file=sys.stderr)
        sys.exit(1)

    print(f"\nResuming \033[1m{adapter.display_name}\033[0m session \033[36m{cid}\033[0m in \033[34m{workdir}\033[0m...\n")
    adapter.resume(cid, workdir)


def execute_handoff(key: str, target_agent: Optional[str] = None) -> None:
    parts = key.split(":")
    if len(parts) < 3:
        print(f"Invalid session key: {key}", file=sys.stderr)
        sys.exit(1)

    source_agent_name, cid, workdir = parts[0], parts[1], ":".join(parts[2:])
    source_adapter = get_adapter(source_agent_name)
    if not source_adapter:
        print(f"Unknown source agent: {source_agent_name}", file=sys.stderr)
        sys.exit(1)

    title, workdir, user_prompts, assistant_msgs = source_adapter.extract_briefing_context(cid, workdir)
    briefing, title, workdir = build_handoff_briefing(
        source_agent_name, cid, workdir, title, user_prompts, assistant_msgs
    )

    all_targets = ["agy", "opencode", "freebuff", "grok", "kimi"]
    other_targets = [t for t in all_targets if t != source_agent_name]
    options = other_targets + [source_agent_name]

    if not target_agent:
        print("\n\033[1;36mCross-Agent Session Handoff\033[0m")
        print(f"Transferring \033[1m{source_adapter.display_name}\033[0m session: \033[33m{title}\033[0m\n")

        names = {
            "agy": "agy (Antigravity CLI)",
            "opencode": "opencode (OpenCode / DeepSeek Flash Free)",
            "freebuff": "freebuff (Freebuff)",
            "grok": "grok (Grok Build TUI)",
            "kimi": "kimi (Kimi Code)",
            "claude": "claude (Claude Code)",
        }

        print("Select target agent to hand off to:")
        for idx, t in enumerate(options, 1):
            tag = AGENT_TAGS.get(t, f"[{t}]")
            note = " (fork / restart)" if t == source_agent_name else ""
            print(f"  [{idx}] {tag:<20} {names.get(t, t)}{note}")
        print(f"  [{len(options)+1}] Cancel")

        choice = input(f"\nChoice (1-{len(options)+1}): ").strip()
        try:
            c_int = int(choice)
            if 1 <= c_int <= len(options):
                target_agent = options[c_int - 1]
            else:
                print("Handoff cancelled.")
                sys.exit(0)
        except ValueError:
            choice_lower = choice.lower()
            if choice_lower in all_targets:
                target_agent = choice_lower
            else:
                print("Handoff cancelled.")
                sys.exit(0)

    target_adapter = get_adapter(target_agent)
    if not target_adapter:
        print(f"Unknown target agent: {target_agent}", file=sys.stderr)
        sys.exit(1)

    print(f"\nPreparing handoff to \033[1m{target_adapter.display_name}\033[0m in \033[34m{workdir}\033[0m...\n")

    # Save handoff briefing file
    handoff_file = os.path.join(workdir, "HANDOFF.md")
    try:
        with open(handoff_file, "w", encoding="utf-8") as f:
            f.write(briefing)
        print(f"\033[32m✓ Briefing saved to {handoff_file}\033[0m")
    except Exception:
        fallback_file = f"/tmp/handoff_{source_agent_name}_{cid[:8]}.md"
        with open(fallback_file, "w", encoding="utf-8") as f:
            f.write(briefing)
        print(f"\033[32m✓ Briefing saved to {fallback_file}\033[0m")

    # Copy to clipboard
    if copy_to_clipboard(briefing):
        print("\033[32m✓ Briefing copied to clipboard (Ctrl+V)\033[0m")

    print(f"\nLaunching \033[1m{target_adapter.display_name}\033[0m with handoff context...\n")
    target_adapter.receive_handoff(briefing, title, workdir)


def main() -> None:
    this_script = os.path.abspath(sys.argv[0])

    if len(sys.argv) > 1:
        flag = sys.argv[1]
        if flag == "--preview" and len(sys.argv) > 2:
            key = sys.argv[2]
            query = sys.argv[3] if len(sys.argv) > 3 else None
            preview_entry(key, query)
            return
        elif flag == "--list-recent":
            lines = get_recent_unified_lines()
            print("\n".join(lines))
            return
        elif flag == "--list-search":
            query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
            lines = search_all_agents(query)
            print("\n".join(lines))
            return
        elif flag in ("resume", "--resume"):
            if len(sys.argv) > 2:
                target = sys.argv[2]
                key = resolve_session_key(target)
                if key:
                    execute_resume(key)
                    return
                else:
                    print(f"No session found matching '{target}'.", file=sys.stderr)
                    sys.exit(1)
        elif flag in ("handoff", "--handoff"):
            target_agent = None
            filter_agent = None
            query_parts = []
            args = sys.argv[2:]
            i = 0
            while i < len(args):
                if args[i] == "--to" and i + 1 < len(args):
                    target_agent = args[i + 1].lower()
                    i += 2
                elif args[i] in ("--from", "-f") and i + 1 < len(args):
                    filter_agent = args[i + 1].lower()
                    i += 2
                elif args[i] in ("--agy", "--opencode", "--freebuff", "--claude"):
                    filter_agent = args[i][2:]
                    i += 1
                else:
                    query_parts.append(args[i])
                    i += 1
            query = " ".join(query_parts).strip()

            if query:
                resolved = resolve_session_key(query)
                if resolved:
                    execute_handoff(resolved, target_agent)
                    return

            if query:
                matches = search_all_agents(query, filter_agent)
                if not matches:
                    print(f"No sessions found matching '{query}'.")
                    sys.exit(1)
                if len(matches) == 1:
                    selected_key = matches[0].split("\t")[0]
                    execute_handoff(selected_key, target_agent)
                else:
                    fzf_input = "\n".join(matches)
                    fzf_cmd = [
                        "fzf",
                        "--ansi",
                        "--delimiter=\t",
                        "--with-nth=2",
                        f"--preview={this_script} --preview {{1}} {{q}}",
                        "--preview-window=right:55%:wrap",
                        f"--header=Found {len(matches)} matching sessions to HAND OFF (ESC to cancel):",
                        "--prompt=Handoff session > ",
                        "--height=85%",
                        "--reverse",
                    ]
                    proc = subprocess.Popen(fzf_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
                    selected, _ = proc.communicate(input=fzf_input)
                    if proc.returncode != 0 or not selected.strip():
                        sys.exit(0)
                    selected_key = selected.split("\t")[0].strip()
                    execute_handoff(selected_key, target_agent)
            else:
                lines = get_recent_unified_lines(filter_agent)
                fzf_input = "\n".join(lines)
                header_info = f" for [{filter_agent}]" if filter_agent else ""
                fzf_cmd = [
                    "fzf",
                    "--ansi",
                    "--delimiter=\t",
                    "--with-nth=2",
                    f"--preview={this_script} --preview {{1}} {{q}}",
                    "--preview-window=right:55%:wrap",
                    f"--header=Select session{header_info} to HAND OFF to another agent (ESC to cancel):",
                    "--prompt=Handoff session > ",
                    "--height=85%",
                    "--reverse",
                ]
                proc = subprocess.Popen(fzf_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
                selected, _ = proc.communicate(input=fzf_input)
                if proc.returncode != 0 or not selected.strip():
                    sys.exit(0)
                selected_key = selected.split("\t")[0].strip()
                execute_handoff(selected_key, target_agent)
            return
        elif flag in ("relay", "--relay"):
            target_agent = None
            custom_cascade = None
            source_cid = None
            auto_confirm = False
            dry_run = False
            args = sys.argv[2:]
            i = 0
            while i < len(args):
                if args[i] == "--to" and i + 1 < len(args):
                    target_agent = args[i + 1].lower()
                    i += 2
                elif args[i] == "--cascade" and i + 1 < len(args):
                    custom_cascade = [a.strip().lower() for a in args[i + 1].split(",")]
                    i += 2
                elif args[i] in ("-y", "--yes"):
                    auto_confirm = True
                    i += 1
                elif args[i] in ("-d", "--dry-run"):
                    dry_run = True
                    i += 1
                elif not args[i].startswith("-"):
                    source_cid = args[i]
                    i += 1
                else:
                    i += 1
            execute_relay(
                source_target=source_cid,
                target_agent=target_agent,
                custom_cascade=custom_cascade,
                auto_confirm=auto_confirm,
                dry_run=dry_run,
            )
            return
        elif flag in ("-h", "--help"):
            print("Usage: agentr [OPTIONS] [QUERY]")
            print("\nUniversal conversation search, session resume & cross-agent handoff:")
            print("  • Antigravity (agy)")
            print("  • OpenCode (with DeepSeek Flash Free)")
            print("  • Freebuff")
            print("  • Grok Build (xAI)")
            print("  • Kimi Code (Moonshot AI)")
            print("  • Claude Code (experimental)")
            print("\nArguments:")
            print("  QUERY             Search term to deep search across all agent transcripts.")
            print("\nOptions:")
            print("  relay [CID]       Instant free-tier relay from throttled agent to next fallback.")
            print("                    Flags: --to <target>, --cascade <a1,a2...>, -y/--yes")
            print("  handoff [QUERY]   Hand off a session to another agent (e.g. agentr handoff HDD --to agy)")
            print("                    Flags: --to <agy|opencode|freebuff|grok|kimi|claude>")
            print("                           --from <agent> or --agy|--opencode|--freebuff|--grok|--kimi")
            print("  --agy             Filter to Antigravity sessions only.")
            print("  --opencode        Filter to OpenCode sessions only.")
            print("  --freebuff        Filter to Freebuff sessions only.")
            print("  -s, --search Q    Deep search all transcripts for Q.")
            print("  -l, --list        Print unified recent sessions to stdout.")
            print("  -h, --help        Show this help message.")
            print("\nInteractive Keys inside picker:")
            print("  Enter             Resume the selected agent session natively.")
            print("  Ctrl+T            Transfer / Hand off the selected session to another agent!")
            print("  Ctrl+F            Toggle deep full-text transcript search across all agents.")
            print("  Ctrl+R            Toggle back to recent unified sessions.")
            print("  Esc               Cancel.")
            return
        elif flag in ("-l", "--list"):
            for line in get_recent_unified_lines():
                parts = line.split("\t")
                if len(parts) > 1:
                    print(parts[1])
            return

    filter_agent = None
    args = sys.argv[1:]
    if "--agy" in args:
        filter_agent = "agy"
        args.remove("--agy")
    elif "--opencode" in args:
        filter_agent = "opencode"
        args.remove("--opencode")
    elif "--freebuff" in args:
        filter_agent = "freebuff"
        args.remove("--freebuff")

    initial_query = ""
    is_deep_search = False

    if args:
        if args[0] in ("-s", "--search", "search"):
            initial_query = " ".join(args[1:])
            is_deep_search = True
        elif not args[0].startswith("-"):
            initial_query = " ".join(args)
            is_deep_search = True

    if is_deep_search and initial_query:
        lines = search_all_agents(initial_query, filter_agent)
        prompt_str = f'Search ("{initial_query}") > '
    else:
        lines = get_recent_unified_lines(filter_agent)
        prompt_str = "Resume agent session > "

    if not lines:
        if is_deep_search:
            print(f"No agent conversations found matching '{initial_query}'.")
        else:
            print("No agent conversations found.")
        sys.exit(0)

    if not sys.stdout.isatty():
        for line in lines:
            parts = line.split("\t")
            if len(parts) > 1:
                print(parts[1])
        return

    fzf_input = "\n".join(lines)
    header_text = "[Enter] Resume  │  [Ctrl+T] Handoff / Transfer  │  [Ctrl+F] Deep Search  │  [Esc] Cancel"

    fzf_cmd = [
        "fzf",
        "--ansi",
        "--delimiter=\t",
        "--with-nth=2",
        "--expect=ctrl-t",
        f"--preview={this_script} --preview {{1}} {{q}}",
        "--preview-window=right:55%:wrap",
        f"--header={header_text}",
        f"--prompt={prompt_str}",
        f"--bind=ctrl-f:reload({this_script} --list-search {{q}})+change-prompt(Deep Search > )",
        f"--bind=ctrl-r:reload({this_script} --list-recent)+change-prompt(Resume agent session > )",
        "--height=85%",
        "--reverse",
    ]

    try:
        proc = subprocess.Popen(
            fzf_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
        )
        selected, _ = proc.communicate(input=fzf_input)
        if proc.returncode != 0 or not selected.strip():
            sys.exit(0)

        lines = selected.strip().split("\n")
        key_pressed = None
        selected_line = ""

        if len(lines) == 1:
            selected_line = lines[0]
        elif len(lines) >= 2:
            key_pressed = lines[0].strip()
            selected_line = lines[1]

        if not selected_line:
            sys.exit(0)

        key = selected_line.split("\t")[0].strip()

        if key_pressed == "ctrl-t":
            execute_handoff(key)
        else:
            execute_resume(key)

    except FileNotFoundError:
        print("Error: 'fzf' is required for interactive selection. Install with: sudo pacman -S fzf", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
