"""
agentr.dispatch: Multi-agent task dispatcher supporting Herdr pane splitting,
                 workspaces, headless execution, and native Antigravity /teamwork prompts.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from typing import Optional, Tuple, Dict, Any

from .board import load_board, update_task_status
from .adapters import get_adapter


def format_teamwork_prompt(
    title: str,
    description: str = "",
    workdir: Optional[str] = None,
    flavor: str = "small",
    criteria: Optional[list] = None
) -> str:
    """Format a task prompt according to Antigravity's native /teamwork protocol.

    Flavors:
      - 'small': Single self-contained fix/feature (1 implementer + adversarial reviewers).
      - 'full': Multi-phase build, research, or complex architecture.
      - 'proof' or 'large': Massive parallel exploration / formal proofs.
      - 'review': Document, code, or spec review.
    """
    flavor = (flavor or "small").strip().lower()
    workdir_path = os.path.abspath(workdir or os.getcwd())

    scale_directive = ""
    if flavor in ("small", "focused", "fix"):
        scale_directive = "This is a single self-contained fix; keep it small and focused.\n\n"
    elif flavor in ("large", "proof", "swarm"):
        scale_directive = "Use a very large team of agents.\n\n"
    elif flavor in ("review", "audit"):
        scale_directive = "Review this implementation thoroughly and document findings.\n\n"

    desc_text = (description or title).strip()

    acc_criteria = criteria or [
        "Code compiles and passes all local test suites without regressions",
        "Implementation addresses the issue cleanly with zero unexpected side effects",
        "Update AgentR board: `agentr task update <ID> done`"
    ]
    criteria_lines = "\n".join(f"- [ ] {c}" for c in acc_criteria)

    prompt = (
        f"{scale_directive}"
        f"Goal: {title}\n\n"
        f"Working directory: {workdir_path}\n"
        f"Integrity mode: development\n\n"
        f"## Requirements\n\n"
        f"### R1. Primary Deliverable\n"
        f"{desc_text}\n\n"
        f"## Acceptance Criteria\n\n"
        f"### Verification\n"
        f"{criteria_lines}\n"
    )
    return prompt


def get_current_herdr_pane() -> Optional[str]:
    """Retrieve the active or current Herdr pane ID."""
    try:
        res = subprocess.run(["herdr", "pane", "current"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            pid = data.get("result", {}).get("pane", {}).get("pane_id")
            if pid:
                return pid
    except Exception:
        pass

    try:
        res = subprocess.run(["herdr", "pane", "list"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            panes = data.get("result", {}).get("panes", [])
            for p in panes:
                if p.get("focused"):
                    return p.get("pane_id")
            if panes:
                return panes[0].get("pane_id")
    except Exception:
        pass
    return None


def dispatch_to_herdr_pane(
    pane_id: Optional[str],
    agent_cmd: str,
    briefing: str,
    workdir: Optional[str] = None,
    direction: str = "right"
) -> Tuple[bool, str]:
    """Split a Herdr pane and launch an agent with the task briefing."""
    target_pane = pane_id or get_current_herdr_pane()
    if not target_pane:
        return False, "Could not determine Herdr pane to split. Is Herdr running?"

    abs_workdir = os.path.abspath(workdir or os.getcwd())

    split_cmd = ["herdr", "pane", "split", target_pane, "--direction", direction]
    if os.path.isdir(abs_workdir):
        split_cmd.extend(["--cwd", abs_workdir])

    try:
        res = subprocess.run(split_cmd, capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return False, f"herdr pane split failed: {res.stderr.strip()}"

        data = json.loads(res.stdout)
        new_pane_id = data.get("result", {}).get("pane", {}).get("pane_id")
        if not new_pane_id:
            return False, "No new pane returned by herdr"

        # Give shell time to initialize in new pane
        time.sleep(0.3)

        agent_clean = (agent_cmd or "agy").strip().lower()
        escaped_prompt = briefing.replace('"', '\\"').replace('$', '\\$')

        if agent_clean == "agy":
            # Launch agy with prompt
            cmd = f'agy --dangerously-skip-permissions -p "{escaped_prompt}"'
        elif agent_clean == "opencode":
            # Launch opencode with auto prompt
            cmd = f'opencode --auto --prompt "{escaped_prompt}"'
        elif agent_clean == "freebuff":
            cmd = f'freebuff -p "{escaped_prompt}"'
        elif agent_clean == "grok":
            cmd = f'grok --always-approve -p "{escaped_prompt}"'
        else:
            cmd = f'{agent_clean} "{escaped_prompt}"'

        subprocess.run(["herdr", "pane", "send-text", new_pane_id, cmd], capture_output=True, text=True)
        subprocess.run(["herdr", "pane", "send-keys", new_pane_id, "enter"], capture_output=True, text=True)

        return True, new_pane_id
    except Exception as e:
        return False, str(e)


def dispatch_to_herdr_workspace(
    label: str,
    agent_cmd: str,
    briefing: str,
    workdir: Optional[str] = None
) -> Tuple[bool, str, str]:
    """Create a new Herdr workspace and start the agent in its root pane."""
    abs_workdir = os.path.abspath(workdir or os.getcwd())
    clean_label = label.strip() or f"Worker-{int(time.time())}"

    try:
        cmd = ["herdr", "workspace", "create", "--label", clean_label, "--cwd", abs_workdir]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return False, "", f"Failed to create workspace: {res.stderr.strip()}"

        data = json.loads(res.stdout)
        result = data.get("result", {})
        root_pane = result.get("root_pane", {})
        workspace = result.get("workspace", {})
        pane_id = root_pane.get("pane_id")
        ws_id = workspace.get("workspace_id")

        if not pane_id:
            return False, "", "Workspace created but root pane missing"

        time.sleep(0.3)
        agent_clean = (agent_cmd or "agy").strip().lower()
        escaped_prompt = briefing.replace('"', '\\"').replace('$', '\\$')

        if agent_clean == "agy":
            cmd = f'agy --dangerously-skip-permissions -p "{escaped_prompt}"'
        elif agent_clean == "opencode":
            cmd = f'opencode --auto --prompt "{escaped_prompt}"'
        elif agent_clean == "freebuff":
            cmd = f'freebuff -p "{escaped_prompt}"'
        elif agent_clean == "grok":
            cmd = f'grok --always-approve -p "{escaped_prompt}"'
        else:
            cmd = f'{agent_clean} "{escaped_prompt}"'

        subprocess.run(["herdr", "pane", "send-text", pane_id, cmd], capture_output=True, text=True)
        subprocess.run(["herdr", "pane", "send-keys", pane_id, "enter"], capture_output=True, text=True)

        return True, ws_id, pane_id
    except Exception as e:
        return False, "", str(e)
