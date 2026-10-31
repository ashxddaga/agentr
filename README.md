# agentr

> **Universal session search, native resume, and zero-loss cross-agent handoff bridge for terminal AI coding agents.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero%20Python%20Deps-orange.svg)](#requirements)

---

## The Problem

Modern AI developers don't rely on just one agent. You might use **Antigravity CLI** (`agy`) for deep architectural reasoning and complex refactoring, **OpenCode** for multi-model flexibility, **Freebuff** for rapid iterative edits, and **Claude Code** for specialized terminal tasks.

However, each agent maintains its own isolated ecosystem:
* Sessions are locked inside proprietary SQLite databases, JSONL logs, or custom binary states.
* Resuming past work requires memorizing disparate CLI flags (`agy resume`, `opencode -s <id>`, `freebuff --continue <timestamp>`, `claude --resume`).
* When an agent hits a dead end or you want to switch engines, you're forced to manually copy-paste terminal history, explain what was already tried, and reconstruct lost context.

**`agentr` solves this.** It acts as a unified hub for all your terminal AI coding sessions: search across all agent histories in one interactive fuzzy UI, resume any session in its original directory with a single keystroke, or hand off an active session to a completely different agent with zero context loss.

---

## Features

- 🔍 **Unified Interactive Fuzzy Search**: Instant `fzf` UI displaying sessions across all detected agents, sorted by recent activity with live transcript previews.
- ⚡ **Native One-Key Resume**: Press <kbd>Enter</kbd> to launch the correct agent CLI with its native resume command, automatically `cd`-ing into the session's workspace.
- 🔄 **Zero-Loss Cross-Agent Handoff**: Press <kbd>Ctrl+T</kbd> to switch any session to another agent. `agentr` extracts the original task prompt, workspace path, and recent assistant decisions into a structured briefing, and boots the target agent ready to continue.
- 🪂 **Free-Tier Token Relay**: Hit a 429 rate limit or exhausted daily plan credits? Run `agentr relay` to instantly transfer the active task to the next free fallback agent in your cascade chain (`agy` → `opencode` → `freebuff` → `grok`) without losing context.
- 📋 **Multi-Agent Project Coordination**: Role-based project blackboards (`agentr board`, `agentr task add`, `agentr task dispatch`) allowing teams of agents (Architect $\to$ Coder $\to$ Reviewer) to collaborate autonomously on complex repos.
- 🔁 **Autonomous Feedback Loop**: Agents working on projects can log bug reports and feature requests directly back to `agentr` with `agentr feedback "<text>"`.
- 🔎 **Deep Transcript Search**: Search conversation logs across every agent database for past debugging decisions, code snippets, or error traces.
- 🪶 **Zero External Python Dependencies**: Built 100% on Python standard library (`sqlite3`, `json`, `subprocess`, `urllib`).

---

## Agent Compatibility Matrix

| Agent | Detection | List & Search | Live Preview | Native Resume | Handoff Receiver | Storage Format |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **Antigravity CLI** (`agy`) | ✅ | ✅ | ✅ | `agy resume <cid>` | `agy -i "<briefing>"` | SQLite `state.db` + JSONL |
| **OpenCode** (`opencode`) | ✅ | ✅ | ✅ | `opencode -s <id>` | `opencode --prompt "<briefing>"` | SQLite `opencode.db` (v1/v2) |
| **Freebuff** (`freebuff`) | ✅ | ✅ | ✅ | `freebuff --continue <ts>` | Seeded session + `--continue` | `~/.config/manicode/` JSON |
| **Grok Build** (`grok`) | ✅ | ✅ | ✅ | `grok -c` | `grok "<briefing>"` | SQLite `session_search.sqlite` |
| **Kimi Code** (`kimi`) | ✅ | ✅ | ✅ | `kimi -S <id>` | `kimi "<briefing>"` | `~/.kimi-code/` JSON & JSONL |
| **Claude Code** (`claude`) | 🧪 Beta | ✅ | ✅ | `claude --resume` | `claude -p "<briefing>"` | `~/.claude/projects/` |

---

## Interactive Controls

When running `agentr`, you are presented with a unified interactive fuzzy finder:

```text
> search sessions...
[AGY]      2026-10-27 08:35  agentr packaging & github prep       ~/Work/agentr
[OPENCODE] 2026-10-26 21:14  datarescue sqlite index optimizer    ~/Work/DataRescue
[FREEBUFF] 2026-10-26 18:02  fix handbag tech pack svg pricking   ~/Work/handbag
--------------------------------------------------------------------------------
Preview:
[USER]: Prepare agentr as a standalone GitHub project...
[ASSISTANT]: Initializing workspace structure, writing adapters and test suite...
```

| Key | Action |
|---|---|
| <kbd>Enter</kbd> | **Resume Session**: Instantly resumes the selected session natively in its original directory. |
| <kbd>Ctrl+T</kbd> | **Handoff Session**: Prompts for target agent (`agy`, `opencode`, `freebuff`, `claude`), builds context briefing, and boots target agent. |
| <kbd>Ctrl+F</kbd> | **Deep Transcript Search**: Prompts for a search term to find across all agent transcripts. |
| <kbd>Ctrl+R</kbd> | **Refresh**: Reloads all agent sessions from disk. |
| <kbd>Esc</kbd> / <kbd>Ctrl+C</kbd> | Exit cleanly. |

---

## CLI Usage

In addition to interactive mode, `agentr` provides full command-line scripting support:

```bash
# Launch interactive fuzzy switcher
agentr

# Free-tier token relay (automatically transfers stalled/throttled task to next free agent)
agentr relay
agentr relay --to freebuff
agentr relay --cascade opencode,freebuff
agentr relay --dry-run

# Multi-agent project blackboard & task coordination
agentr board                                                      # View project BOARD.md
agentr task add "Build REST API" --agent opencode --review grok   # Add task
agentr task update task-01 in_progress                            # Update status
agentr task dispatch task-01                                      # Dispatch task to agent
agentr feedback "Found issue with CORS headers" --from grok       # Log autonomous feedback

# SolidCraft MCP Diagnostics & Parametric CAD Verification
agentr cad probe                                                  # Live version & #8191 expression probe
agentr cad bench                                                  # Mount-plate geometric verification benchmark
agentr cad report                                                 # Generate full markdown benchmark report

# Deep search transcript contents across all agents
agentr search "database migration"

# Native resume by session ID or prefix
agentr resume c9d5c5cb-c5bd-4826-91ba-06f2c9915380

# Direct handoff of a session to another agent
agentr handoff c9d5c5cb --to freebuff
agentr handoff 1740582000 --to agy

# Dump preview of a session
agentr --preview <session-id>

# List all detected sessions in raw tab-separated format
agentr --list
```

---

## How Handoff Works

When transferring a session between agents (e.g. from `agy` to `freebuff` or `opencode`):

```text
 ┌─────────────────────────────────────────────────────────┐
 │ Source Session (Antigravity CLI / OpenCode / Freebuff) │
 └────────────────────────────┬────────────────────────────┘
                              │
                    extract briefing context
                              ▼
 ┌─────────────────────────────────────────────────────────┐
 │ agentr Context Distillation Engine                      │
 │ - Original user goal & prompt                           │
 │ - Working directory context                             │
 │ - Recent actions, tool executions & resolutions         │
 │ - Strips encrypted reasoning blocks & binary data       │
 └────────────────────────────┬────────────────────────────┘
                              │
                    structured briefing
                              ▼
 ┌─────────────────────────────────────────────────────────┐
 │ Target Agent Adapter Dispatch                           │
 │ - agy: launches with -i "<briefing>" in session workdir │
 │ - opencode: launches with --prompt "<briefing>"         │
 │ - freebuff: seeds chat JSON state & executes --continue │
 │ - claude: launches with -p "<briefing>"                 │
 └─────────────────────────────────────────────────────────┘
```

The target agent starts immediately with full comprehension of what happened before, eliminating redundant work and repetitive explanations.

---

## Architecture

`agentr` is built using an extensible adapter architecture:

```text
agentr/
  ├── core.py             # Data models, briefing generator, clipboard fallbacks
  ├── cli.py              # fzf interaction, CLI dispatch, deep search runner
  ├── relay.py            # Token exhaustion detection & free-tier cascading
  └── adapters/
      ├── base.py         # BaseAgentAdapter protocol
      ├── agy.py          # Antigravity CLI adapter (SQLite + JSONL)
      ├── opencode.py     # OpenCode adapter (SQLite v1 & v2)
      ├── freebuff.py     # Freebuff adapter (JSON state & chat seeding)
      └── claude.py       # Claude Code adapter (experimental)
```

Adding support for any new agent requires only implementing `BaseAgentAdapter`:
1. `detect()`: Check binary or config presence.
2. `list_sessions()`: Parse session titles, timestamps, and workspace directories.
3. `search(query)`: Search transcripts for matching terms.
4. `preview(cid)`: Format transcript preview for terminal display.
5. `resume(cid, workdir)`: Launch native resume command.
6. `extract_briefing_context(cid, workdir)`: Extract user prompts & assistant responses.
7. `receive_handoff(briefing, title, workdir)`: Launch target agent with injected briefing.

---

## Multi-Agent Roadmap

- [x] **Phase 1: Foundation (Current - v0.2.1)**
  - Full adapter support for Antigravity CLI, OpenCode, and Freebuff.
  - Experimental Claude Code adapter.
  - Interactive `fzf` browser with real-time transcript preview.
  - Zero-loss cross-agent handoff matrix.
  - Token Exhaustion Relay: Instant cascade and 1-key relay across free tiers on rate limit (429).
  - Deep transcript search across SQLite and JSONL sources.
  - Standalone packaging with zero external Python dependencies.

- [ ] **Phase 2: Agent Ecosystem Expansion (v0.3)**
  - [ ] **Aider Adapter**: Parse `.aider.chat.history.md` and resume via `aider --restore-chat-history`.
  - [ ] **OpenAI Codex CLI Adapter**: Session indexing and handoff receiver.
  - [ ] **Block Goose CLI Adapter**: Goose toolkit session discovery and resume.
  - [ ] **Ampere Adapter**: Integrate with Ampere autonomous agent sessions.

- [ ] **Phase 3: Intelligence & Management (v0.4)**
  - [ ] **Session Tagging & Bookmarks**: Star or tag critical sessions across agents (`#bugfix`, `#architecture`).
  - [ ] **Multi-Session Diff View**: Compare how two different agents approached the same task.
  - [ ] **Token & Cost Dashboard**: Estimate tokens consumed across sessions and agents.

- [ ] **Phase 4: Semantic Search & Export (v0.5)**
  - [ ] **Semantic Vector Search**: Local vector embeddings for conceptual search across all transcripts.
  - [ ] **HTML / Markdown Export**: Generate clean, shareable run reports or postmortems from any session.

---

## Installation

### Prerequisites
* Python 3.9+
* [`fzf`](https://github.com/junegunn/fzf) (for interactive fuzzy mode)
* `wl-clipboard` (Wayland) or `xclip` / `xsel` (X11) for system clipboard fallback

### Direct Symlink (Recommended)
Clone the repository and symlink `bin/agentr` into your `PATH`:

```bash
git clone https://github.com/ashxddaga/agentr.git ~/Work/agentr
ln -sfn ~/Work/agentr/bin/agentr ~/.local/bin/agentr
```

### Editable Pip Install
```bash
git clone https://github.com/ashxddaga/agentr.git
cd agentr
pip install -e .
```

---

## Running Tests

`agentr` includes a unit test suite testing core utilities, adapter detection, and cross-agent handoff briefing generation:

```bash
python3 -m unittest discover tests
```

---

## Contributing

Contributions are welcome! If you use a terminal coding agent that isn't supported yet, please feel free to submit an adapter PR:

1. Fork this repository.
2. Create a new adapter file in `agentr/adapters/<your_agent>.py` subclassing `BaseAgentAdapter`.
3. Register your adapter in `agentr/adapters/__init__.py`.
4. Add unit tests in `tests/test_adapters.py`.
5. Submit a Pull Request.

---

## License

MIT License © 2026 Ashish Daga
