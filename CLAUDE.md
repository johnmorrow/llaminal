# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Llaminal

Llaminal is a **shell wrapper with AI**. The user launches `llaminal`, gets their normal shell ($SHELL) running in a PTY, and double-taps Escape to toggle into AI mode. The AI passively captures recent shell output (via pyte) for context. It talks to local LLMs via OpenAI-compatible APIs (llama.cpp, ollama, vLLM), streams responses with Rich Live rendering, supports tool calling, and persists conversations in SQLite.

## Commands

```bash
# Install in dev mode
pip install -e .

# Run (launches your $SHELL with AI overlay — auto-detects running servers)
llaminal
llaminal --base-url http://localhost:8080 --model local-model
llaminal --port 8080                      # shorthand for --base-url http://localhost:8080
llaminal --api-key sk-... --temperature 0.7
llaminal --system-prompt "..."
llaminal --shell /bin/bash                # override $SHELL

# API key can also be set via env var
export LLAMINAL_API_KEY=sk-...

# Config file (optional): ~/.config/llaminal/config.toml
# Supported keys: base_url, port, model, api_key, temperature, system_prompt, mood, theme, stats, shell, context_lines
llaminal --config /path/to/alt/config.toml

# Session management
llaminal --history             # list past sessions
llaminal --resume last         # resume most recent session
llaminal --resume <session-id> # resume specific session

# Personality & display
llaminal --mood pirate         # persona presets: pirate, poet, senior-engineer, eli5, concise, rubber-duck
llaminal --theme dracula       # color themes: default, light, solarized, dracula, catppuccin, llama
llaminal --stats               # show token/sec and latency after each response
llaminal --context-lines 50    # lines of terminal scrollback to capture as AI context

# No tests or linting configured yet
```

## Usage

1. Launch `llaminal` — your normal shell starts (with .zshrc, aliases, etc.)
2. Use the shell normally (ls, cd, vim, git, etc.)
3. Double-tap Escape → enters AI mode (🦙> prompt)
4. Type a question and press Enter → AI responds with streaming + markdown
5. Single Escape or Ctrl+D → returns to shell
6. AI automatically sees recent terminal output as context

## Architecture

The source lives in `src/llaminal/` with entry point `cli.py:main()`.

```
┌─────────────────────────────────────────────────┐
│  llaminal process (parent)                       │
│  asyncio event loop                               │
│  ├─ stdin reader → shell or AI input             │
│  ├─ master_fd reader → stdout + pyte scrollback  │
│  └─ AI mode: run_agent_loop() (already async)    │
│  pyte Screen — rolling scrollback buffer          │
│  Mode flag: SHELL | AI                            │
└────────────────┬────────────────────────────────┘
                 │ PTY (master_fd ↔ slave_fd)
┌────────────────┴────────────────────────────────┐
│  child process: user's $SHELL                    │
└──────────────────────────────────────────────────┘
```

**Core flow**: PTY proxy in shell mode → double-ESC toggles AI mode → user input sent to `agent.py:run_agent_loop()` which streams via Rich Live → tool calls executed via registry → messages saved to SQLite → return to AI prompt or shell.

**Key modules**:
- `cli.py` — Click CLI setup, config resolution, launches ShellWrapper + AIMode, wires up pyte scrollback capture. No banner, no prompt_toolkit.
- `shell.py` — `ShellWrapper` class: PTY spawning (`pty.openpty` + `os.fork` + `os.execv`), raw mode, asyncio `add_reader` on stdin + master_fd, SIGWINCH forwarding, SIGCHLD handling, double-ESC detection state machine (300ms timeout), mode toggle.
- `ai_mode.py` — `AIMode` class: 🦙> prompt, raw keystroke buffering with line editing (backspace, arrows, home/end, Ctrl+A/E/U), Enter sends to agent loop, single ESC exits, cooked/raw mode switching for Rich output.
- `agent.py` — Agentic loop: stream response, parse tool calls, execute, repeat. Every error path has an actionable user-facing message.
- `client.py` — `LlaminalClient` wraps httpx for async SSE streaming to `/v1/chat/completions`.
- `session.py` — Manages OpenAI-format message history; `set_shell_context()` injects terminal output into next user message.
- `render.py` — `StreamRenderer` wraps Rich `Live` for token streaming at 10fps with llama thinking animation. Tool call/result panels use active theme.
- `banners.py` — Legacy rotating startup banners (not currently imported).
- `moods.py` — Six mood presets that override the system prompt.
- `themes.py` — Color theme system with six built-in themes.
- `config.py` — Loads `~/.config/llaminal/config.toml`. DEFAULTS include `shell` and `context_lines`.
- `discover.py` — Probes common ports for running LLM servers.
- `storage.py` — SQLite persistence at `~/.local/share/llaminal/history.db`.
- `tools/registry.py` — `Tool` dataclass + `ToolRegistry` for dispatch.
- `tools/bash.py` — Shell execution with user confirmation, 30s timeout.
- `tools/files.py` — `read_file`, `write_file`, `list_files`.

**Patterns**:
- PTY proxy with asyncio `loop.add_reader()` for non-blocking I/O
- Double-ESC detection: ESC → 300ms timer → second ESC toggles AI; timeout/other key forwards ESC to shell
- Terminal mode switching: raw mode for PTY proxy, cooked mode for Rich rendering during AI responses
- pyte virtual terminal captures shell scrollback → injected as context in AI messages
- Fully async (`asyncio` + `httpx.AsyncClient`)
- Graceful degradation: no LLM server → shell works fine, AI mode shows helpful message
- Config precedence: CLI flags > env vars (`LLAMINAL_API_KEY`) > config file > defaults

## Roadmap

The product roadmap lives in `~/Downloads/llaminal-roadmap.md`. The MVP PRD is at `docs/prd/Llaminal_MVP_PRD_Revised.md`. Stage "The Invisible Layer" (shell wrapper pivot) is complete.
