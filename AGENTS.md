# agentr — Universal Agent Session Switcher & Handoff Bridge

Universal terminal session search, native resume, and zero-loss cross-agent
handoff bridge for terminal AI coding agents (Antigravity CLI, OpenCode,
Freebuff, Claude Code, and more).

## 1. What is this?

A modular Python CLI utility with zero external dependencies (leverages `fzf`
and agent CLIs). It aggregates session histories across multiple terminal coding
agents, provides interactive fuzzy search and transcript preview, natively resumes
sessions in their working directories, and extracts contextual briefings to transfer
active work seamlessly across agent boundaries.

## 2. How to run and test it

Run interactive session switcher:
```bash
./bin/agentr
# or if installed/symlinked in ~/.local/bin:
agentr
```

Run CLI deep search or direct commands:
```bash
agentr search <term>
agentr resume <session-id>
agentr handoff <session-id> --to <agy|opencode|freebuff|claude>
agentr --list
```

Run test suite:
```bash
python3 -m unittest discover tests -v
```

Run mandatory pre-push CI gate & quality audit:
```bash
./bin/ci
```
The automated CI gate enforces 6 mandatory checks before any push:
1. Python compilation integrity (`py_compile`)
2. Zero external dependencies audit (stdlib only)
3. Secret and credential leak scan
4. 42 Unit & Integration tests (`unittest`)
5. CLI subcommand sanity (`agentr --help`, `run`, `task`, `msg`)
6. Git working tree cleanliness and hygiene

A git pre-push hook is installed at `.git/hooks/pre-push` to automatically run `./bin/ci` prior to `git push`.

Install locally in editable mode:
```bash
pip install -e .
```

## 3. Where does its data live?

`agentr` does not maintain a private database; it reads and interfaces with native
agent configuration and session storage:

- **Antigravity CLI (`agy`)**: `~/.gemini/antigravity-cli/state.db` and transcript JSONLs under `~/.gemini/antigravity-cli/brain/`.
- **OpenCode**: `~/.local/share/opencode/opencode.db` (SQLite v1 & v2 schemas).
- **Freebuff / Manicode**: `~/.config/manicode/projects/<project-hash>/chats/`.
- **Claude Code**: `~/.claude/projects/`.

## 4. What must I not touch?

- Do not modify or corrupt foreign agent databases (`state.db`, `opencode.db`).
  All session reading is strictly read-only with SQLite URI `?mode=ro`.
- Handoff file creation for Freebuff (`chat-meta.json`, `chat-messages.json`,
  `run-state.json`) must strictly match Bun schema contracts.
- Keep the zero external Python dependencies rule intact (`unittest`, `sqlite3`,
  `json`, `subprocess`, `urllib` only). Terminal interactive UI uses system `fzf`.
