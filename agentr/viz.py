"""
agentr.viz: Multi-agent swarm topology, live coordination radar,
            and cyber-terminal visualization engine for AgentR & AgentDesk.
"""
from __future__ import annotations

import os
import json
import datetime
from typing import Optional, List, Dict, Any

from .board import load_board
from .live_relay import load_live_snapshot

# Visual agent design tokens (colors & roles)
AGENT_THEMES: Dict[str, Dict[str, str]] = {
    "agy": {
        "name": "Antigravity (AGY)",
        "role": "Lead Architect & Deep CAD Refactoring",
        "color": "#38bdf8",     # Cyan / Sky
        "term_color": "\033[1;36m",
        "icon": "⚡",
        "status": "active",
    },
    "opencode": {
        "name": "OpenCode (DeepSeek)",
        "role": "Engine Features & AST Masking",
        "color": "#a855f7",     # Purple / Violet
        "term_color": "\033[1;35m",
        "icon": "🤖",
        "status": "active",
    },
    "grok": {
        "name": "Grok Build (xAI)",
        "role": "Kernel Geometry & Error Triage",
        "color": "#f59e0b",     # Amber / Gold
        "term_color": "\033[1;33m",
        "icon": "🛰️",
        "status": "relayed",
    },
    "freebuff": {
        "name": "Freebuff (Manicode)",
        "role": "Fast Iteration & Component Styling",
        "color": "#10b981",     # Emerald / Mint
        "term_color": "\033[1;32m",
        "icon": "🟢",
        "status": "standby",
    },
    "kimi": {
        "name": "Kimi Code (Moonshot)",
        "role": "Long-Context Audit & Reference Verification",
        "color": "#06b6d4",
        "term_color": "\033[1;36m",
        "icon": "🌙",
        "status": "standby",
    },
    "claude": {
        "name": "Claude Code",
        "role": "Specialized Terminal Pair",
        "color": "#f97316",
        "term_color": "\033[1;31m",
        "icon": "🔶",
        "status": "standby",
    },
}


def get_swarm_graph_data(
    project_dir: Optional[str] = None,
    live_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compile structured telemetry and swarm topology for web dashboards and APIs."""
    base = project_dir or os.getcwd()
    board = load_board(base)
    tasks = board.get("tasks", [])
    feedbacks = board.get("feedback", [])

    if live_context is None:
        try:
            live_context = load_live_snapshot(base)
        except Exception:
            live_context = None

    # Compute task status counts
    done_tasks = [t for t in tasks if t.get("status") == "done"]
    in_progress_tasks = [t for t in tasks if t.get("status") == "in_progress"]
    todo_tasks = [t for t in tasks if t.get("status") in ("todo", "review")]

    # Compute active agents and their assigned workloads
    agent_workload: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        ag = t.get("agent", "agy").lower()
        agent_workload.setdefault(ag, []).append(t)

    agents_list = []
    for key, theme in AGENT_THEMES.items():
        work = agent_workload.get(key, [])
        active_task = next((w for w in work if w.get("status") == "in_progress"), None)
        latest_task = work[-1] if work else None

        status = "idle"
        if active_task:
            status = "working"
        elif any(w.get("status") == "done" for w in work):
            status = "completed"

        if key == "grok" and live_context and live_context.get("errors"):
            status = "relayed"

        agents_list.append({
            "key": key,
            "name": theme["name"],
            "role": theme["role"],
            "color": theme["color"],
            "icon": theme["icon"],
            "status": status,
            "tasks_assigned": len(work),
            "current_task": active_task.get("title") if active_task else (latest_task.get("title") if latest_task else "Available for dispatch"),
            "current_task_id": active_task.get("id") if active_task else (latest_task.get("id") if latest_task else None),
        })

    # Recent relays
    recent_relays = []
    if live_context and live_context.get("errors"):
        for err in live_context.get("errors", []):
            if "limit" in err.get("text", "").lower() or "grok" in err.get("text", "").lower():
                recent_relays.append({
                    "from_agent": "grok",
                    "to_agent": "opencode",
                    "reason": err.get("text", "")[:120],
                    "timestamp": err.get("timestamp", datetime.datetime.now().isoformat()),
                    "status": "cascaded",
                })

    return {
        "project": board.get("project", os.path.basename(base)),
        "updated_at": datetime.datetime.now().isoformat(),
        "stats": {
            "total_tasks": len(tasks),
            "completed": len(done_tasks),
            "in_progress": len(in_progress_tasks),
            "pending": len(todo_tasks),
            "active_agents": len([a for a in agents_list if a["status"] in ("working", "completed")]),
            "relay_events": len(recent_relays),
        },
        "agents": agents_list,
        "tasks": tasks,
        "recent_relays": recent_relays,
        "cad_environment": live_context.get("cad_environment") if live_context else "Active SolidCraft CAD Suite",
    }


def render_terminal_swarm(
    project_dir: Optional[str] = None,
    live_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a high-impact, cyberpunk-styled terminal coordination radar."""
    data = get_swarm_graph_data(project_dir, live_context)
    stats = data["stats"]
    proj = data["project"]

    lines = []
    lines.append("\033[1;35m╔═══════════════════════════════════════════════════════════════════════════════════╗\033[0m")
    lines.append(f"\033[1;35m║\033[0m  \033[1;37m⚡ AGENTR SWARM RADAR & MULTI-AGENT COORDINATION HUB — {proj.upper():<20}\033[0m    \033[1;35m║\033[0m")
    lines.append("\033[1;35m╠═══════════════════════════════════════════════════════════════════════════════════╣\033[0m")
    lines.append(
        f"\033[1;35m║\033[0m  \033[36mTasks:\033[0m \033[1m{stats['total_tasks']}\033[0m  "
        f"\033[32mCompleted:\033[0m \033[1;32m{stats['completed']}\033[0m  "
        f"\033[33mIn-Progress:\033[0m \033[1;33m{stats['in_progress']}\033[0m  "
        f"\033[35mActive Agents:\033[0m \033[1;35m{stats['active_agents']}\033[0m  "
        f"\033[31mRelays:\033[0m \033[1;31m{stats['relay_events']}\033[0m"
        f"{' ' * (22 - len(str(stats['total_tasks'])) - len(str(stats['completed'])) - len(str(stats['in_progress'])) - len(str(stats['active_agents'])) - len(str(stats['relay_events'])))}\033[1;35m║\033[0m"
    )
    lines.append("\033[1;35m╠═══════════════════════════════════════════════════════════════════════════════════╣\033[0m")
    lines.append("\033[1;35m║\033[0m  \033[1;33mACTIVE AGENT FLEET & COOPERATIVE TOPOLOGY:\033[0m                                      \033[1;35m║\033[0m")

    for a in data["agents"]:
        theme = AGENT_THEMES.get(a["key"], {})
        color = theme.get("term_color", "\033[0m")
        status_badge = {
            "working": "\033[1;42;30m WORKING \033[0m",
            "completed": "\033[1;32m✓ COMPLETED\033[0m",
            "relayed": "\033[1;43;30m RELAYED \033[0m",
            "idle": "\033[90mIDLE\033[0m",
        }.get(a["status"], "\033[90mSTANDBY\033[0m")

        lines.append(f"\033[1;35m║\033[0m  {a['icon']} {color}\033[1m{a['name']:<24}\033[0m [{status_badge}]  \033[90m{a['role']}\033[0m")
        task_str = a['current_task']
        if len(task_str) > 65:
            task_str = task_str[:62] + "..."
        lines.append(f"\033[1;35m║\033[0m     └─► \033[37m{task_str}\033[0m")

    lines.append("\033[1;35m╠═══════════════════════════════════════════════════════════════════════════════════╣\033[0m")
    lines.append("\033[1;35m║\033[0m  \033[1;36mLIVE PROJECT BLACKBOARD (RECENT 5 TASKS):\033[0m                                        \033[1;35m║\033[0m")

    for t in data["tasks"][-5:]:
        tid = t.get("id", "??")
        title = t.get("title", "")
        if len(title) > 52:
            title = title[:49] + "..."
        ag = t.get("agent", "agy")
        st = t.get("status", "todo")

        st_badge = {
            "done": "\033[32m[DONE]\033[0m",
            "in_progress": "\033[33m[RUNNING]\033[0m",
            "review": "\033[35m[REVIEW]\033[0m",
            "todo": "\033[90m[TODO]\033[0m",
        }.get(st, "\033[90m[--]\033[0m")

        lines.append(f"\033[1;35m║\033[0m  \033[1;30;47m {tid} \033[0m {st_badge} \033[1m{title:<54}\033[0m \033[35m@{ag:<8}\033[0m \033[1;35m║\033[0m")

    lines.append("\033[1;35m╚═══════════════════════════════════════════════════════════════════════════════════╝\033[0m\n")
    return "\n".join(lines)


def render_html_widget(data: Optional[Dict[str, Any]] = None) -> str:
    """Render an ultra-crisp, cyberpunk animated SVG/HTML swarm visualizer."""
    if data is None:
        data = get_swarm_graph_data()

    agents_json = json.dumps(data["agents"])
    stats_json = json.dumps(data["stats"])
    tasks_json = json.dumps(data["tasks"][-8:])

    return f"""
    <div class="swarm-visualizer-container" id="swarm-container">
      <div class="swarm-header">
        <div class="swarm-title-bar">
          <span class="swarm-icon">⚡</span>
          <span class="swarm-title">AGENTR SWARM RADAR</span>
          <span class="swarm-badge live-pulse">LIVE CO-ORDINATION</span>
        </div>
        <div class="swarm-stats-strip">
          <div class="stat-pill"><span class="stat-val">{data['stats']['total_tasks']}</span> <span class="stat-lbl">Tasks</span></div>
          <div class="stat-pill stat-done"><span class="stat-val">{data['stats']['completed']}</span> <span class="stat-lbl">Done</span></div>
          <div class="stat-pill stat-prog"><span class="stat-val">{data['stats']['in_progress']}</span> <span class="stat-lbl">Active</span></div>
          <div class="stat-pill stat-agents"><span class="stat-val">{data['stats']['active_agents']}</span> <span class="stat-lbl">Agents</span></div>
        </div>
      </div>

      <div class="swarm-topology-canvas">
        <svg class="swarm-svg-net" viewBox="0 0 600 220" preserveAspectRatio="xMidYMid meet">
          <defs>
            <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <linearGradient id="link-grad-1" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="#38bdf8" />
              <stop offset="100%" stop-color="#a855f7" />
            </linearGradient>
            <linearGradient id="link-grad-2" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="#38bdf8" />
              <stop offset="100%" stop-color="#f59e0b" />
            </linearGradient>
            <linearGradient id="link-grad-3" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="#a855f7" />
              <stop offset="100%" stop-color="#10b981" />
            </linearGradient>
          </defs>

          <!-- Dynamic Connection Beams -->
          <line x1="100" y1="110" x2="300" y2="45" stroke="url(#link-grad-1)" stroke-width="2.5" stroke-dasharray="6,4" class="anim-beam-fast" />
          <line x1="100" y1="110" x2="300" y2="175" stroke="url(#link-grad-2)" stroke-width="2.5" stroke-dasharray="6,4" class="anim-beam-rev" />
          <line x1="300" y1="45" x2="500" y2="110" stroke="url(#link-grad-3)" stroke-width="2" stroke-dasharray="4,4" />
          <line x1="300" y1="175" x2="500" y2="110" stroke="#f59e0b" stroke-width="2" stroke-dasharray="4,4" />

          <!-- Nodes: AGY (Hub) -->
          <g class="swarm-node node-agy" transform="translate(100, 110)">
            <circle r="28" fill="#071226" stroke="#38bdf8" stroke-width="2.5" filter="url(#glow)" />
            <circle r="36" fill="none" stroke="#38bdf8" stroke-width="1" opacity="0.4" class="pulse-ring" />
            <text text-anchor="middle" dy="-2" fill="#38bdf8" font-family="monospace" font-size="12" font-weight="bold">AGY</text>
            <text text-anchor="middle" dy="12" fill="#94a3b8" font-family="monospace" font-size="8">ARCHITECT</text>
          </g>

          <!-- Nodes: OpenCode -->
          <g class="swarm-node node-opencode" transform="translate(300, 45)">
            <circle r="25" fill="#1b0b2e" stroke="#a855f7" stroke-width="2" filter="url(#glow)" />
            <text text-anchor="middle" dy="-2" fill="#a855f7" font-family="monospace" font-size="11" font-weight="bold">OPENCODE</text>
            <text text-anchor="middle" dy="11" fill="#94a3b8" font-family="monospace" font-size="8">DEEPSEEK</text>
          </g>

          <!-- Nodes: Grok (Relayed) -->
          <g class="swarm-node node-grok" transform="translate(300, 175)">
            <circle r="25" fill="#241505" stroke="#f59e0b" stroke-width="2" filter="url(#glow)" />
            <text text-anchor="middle" dy="-2" fill="#f59e0b" font-family="monospace" font-size="11" font-weight="bold">GROK</text>
            <text text-anchor="middle" dy="11" fill="#94a3b8" font-family="monospace" font-size="8">RELAYED</text>
          </g>

          <!-- Nodes: SolidCraft Project Blackboard Hub -->
          <g class="swarm-node node-board" transform="translate(500, 110)">
            <rect x="-35" y="-22" width="70" height="44" rx="8" fill="#061e14" stroke="#10b981" stroke-width="2" filter="url(#glow)" />
            <text text-anchor="middle" dy="-4" fill="#10b981" font-family="monospace" font-size="10" font-weight="bold">BOARD.md</text>
            <text text-anchor="middle" dy="10" fill="#6ee7b7" font-family="monospace" font-size="8">18 TASKS</text>
          </g>
        </svg>
      </div>

      <!-- Agent Cards Grid -->
      <div class="swarm-agent-grid">
        <div class="agent-card card-agy">
          <div class="agent-card-header">
            <span class="agent-badge badge-agy">⚡ AGY (ANTIGRAVITY)</span>
            <span class="status-indicator status-live">ACTIVE LEAD</span>
          </div>
          <div class="agent-card-role">Lead Architect & Deep CAD Refactorer</div>
          <div class="agent-card-focus">
            <span class="focus-label">LATEST PR:</span>
            <a href="https://github.com/tangency-labs/solidcraft/pull/9958" target="_blank" class="focus-link">#9958 (Fix #9940: UI Font Bold)</a>
          </div>
        </div>

        <div class="agent-card card-opencode">
          <div class="agent-card-header">
            <span class="agent-badge badge-opencode">🤖 OPENCODE</span>
            <span class="status-indicator status-live">FEATURE WORKER</span>
          </div>
          <div class="agent-card-role">Engine Features & Axis Masking (DeepSeek Flash)</div>
          <div class="agent-card-focus">
            <span class="focus-label">FOCUS:</span>
            <a href="https://github.com/tangency-labs/solidcraft/issues/9946" target="_blank" class="focus-link">Issue #9946: Single-Axis Align</a>
          </div>
        </div>

        <div class="agent-card card-grok">
          <div class="agent-card-header">
            <span class="agent-badge badge-grok">🛰️ GROK / RELAY</span>
            <span class="status-indicator status-relayed">CASCADE RELAY</span>
          </div>
          <div class="agent-card-role">Kernel Diagnostics & Triage Fallback</div>
          <div class="agent-card-focus">
            <span class="focus-label">DIAGNOSIS:</span>
            <a href="https://github.com/tangency-labs/solidcraft/issues/9939" target="_blank" class="focus-link">Issue #9939: Fillet Non-Planar Error</a>
          </div>
        </div>
      </div>
    </div>
    """
