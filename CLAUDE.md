# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Llaminal

Llaminal is an agentic CLI that talks to local LLMs via OpenAI-compatible APIs (llama.cpp, ollama, vLLM). It streams responses with Rich Live rendering, supports tool calling, and persists conversations in SQLite.

## Commands

```bash
# Install in dev mode
pip install -e .

# Run the CLI (auto-detects running servers if no URL specified)
llaminal
llaminal --base-url http://localhost:8080 --model local-model
llaminal --port 8080                      # shorthand for --base-url http://localhost:8080
llaminal --api-key sk-... --temperature 0.7
llaminal --system-prompt "..."

# API key can also be set via env var
export LLAMINAL_API_KEY=sk-...

# Config file (optional): ~/.config/llaminal/config.toml
# Supported keys: base_url, port, model, api_key, temperature, system_prompt, mood, theme, stats, sound, quiet
llaminal --config /path/to/alt/config.toml

# Session management
llaminal --history             # list past sessions
llaminal --resume last         # resume most recent session
llaminal --resume <session-id> # resume specific session

# Personality & display
llaminal --mood pirate         # persona presets: pirate, poet, senior-engineer, eli5, concise, rubber-duck
llaminal --theme dracula       # color themes: default, light, solarized, dracula, catppuccin, llama
llaminal --stats               # show token/sec and latency after each response
llaminal --sound               # terminal bell when long responses finish (>3s)
llaminal --quiet               # suppress startup banner

# No tests or linting configured yet
```

## Architecture

The source lives in `src/llaminal/` with entry point `cli.py:main()`.

**Core loop**: User input → `agent.py:run_agent_loop()` streams the LLM response via Rich Live → if tool calls are present, executes them via the tool registry, appends results to session history, and re-prompts the model. The loop exits when the model produces plain text with no tool calls. Messages are auto-saved to SQLite after each exchange.

**Key modules**:
- `cli.py` — Click CLI setup, prompt loop, server auto-detection, session resume/history. Resolves all settings with precedence chain.
- `agent.py` — Agentic loop: stream response, parse tool calls, execute, repeat. Every error path has an actionable user-facing message (connection refused, auth failure, timeout, etc).
- `client.py` — `LlaminalClient` wraps httpx for async SSE streaming to `/v1/chat/completions`. Supports API key auth (Bearer token) and temperature. Skips malformed JSON chunks.
- `session.py` — Manages OpenAI-format message history; contains the default system prompt
- `render.py` — `StreamRenderer` class wraps Rich `Live` for word-wrapped token streaming at 10fps. Includes a pac-man style llama-eating-dots thinking animation (background thread) and optional token/sec stats. On completion, `finalize()` replaces streamed text with rendered Markdown. Tool call panels, result panels, and errors all use the active theme.
- `banners.py` — Rotating startup banners with llama art variants (classic, chill, wink, sleepy) and random one-liners. Uses active theme for colors.
- `moods.py` — Six mood presets that override the system prompt: pirate, poet, senior-engineer, eli5, concise, rubber-duck.
- `themes.py` — Color theme system with semantic roles (accent, llama_body, tool_border, etc). Six built-in themes: default, light, solarized, dracula, catppuccin, llama. Module-level `get_theme()`/`set_theme()` for global access.
- `config.py` — Loads `~/.config/llaminal/config.toml` (TOML via tomllib/tomli). `resolve()` applies precedence: CLI flags > env vars > config file > defaults.
- `discover.py` — Probes ports 8080, 11434, 8000, 5000, 1234 for running LLM servers via `GET /v1/models`. Auto-connects if one found, prompts if multiple.
- `storage.py` — `Storage` class wraps SQLite at `~/.local/share/llaminal/history.db`. Sessions table + messages table. Auto-titles sessions from first user message. Supports create, save, load, list, get_latest.
- `tools/registry.py` — `Tool` dataclass + `ToolRegistry` for dispatch; converts tools to OpenAI function-calling schema. Returns error strings for unknown tools and tool exceptions (never raises).
- `tools/bash.py` — Shell execution with user confirmation, 30s timeout, structured output (stdout/stderr/exit_code/timed_out), shows working directory
- `tools/files.py` — `read_file` (100KB size cap, binary detection), `write_file` (diff preview on overwrite), `list_files` (200 result cap). All paths support `~` expansion.

**Patterns**:
- Fully async (`asyncio` + `httpx.AsyncClient`)
- Streaming via Rich Live with automatic word-wrap and terminal resize handling
- Destructive tools (bash, write_file) require user confirmation before execution
- Tools are registered as `Tool` dataclasses with JSON Schema parameters and async `execute` callables
- Error resilience: tool failures return error strings to model, network errors preserve session, Ctrl+C saves partial content
- Config precedence: CLI flags > env vars (`LLAMINAL_API_KEY`) > config file > defaults

## Roadmap

The product roadmap lives in `~/Downloads/llaminal-roadmap.md`. The MVP PRD is at `docs/prd/Llaminal_MVP_PRD_Revised.md`. Stages 1 ("Solid Ground") and 2 ("Alive") are complete.
