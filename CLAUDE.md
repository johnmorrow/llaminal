# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Llaminal

Llaminal is an agentic CLI that talks to local LLMs via OpenAI-compatible APIs (llama.cpp, ollama, vLLM). It streams responses, supports tool calling, and renders output with Rich.

## Commands

```bash
# Install in dev mode
pip install -e .

# Run the CLI
llaminal
llaminal --base-url http://localhost:8080 --model local-model
llaminal --port 8080                      # shorthand for --base-url http://localhost:8080
llaminal --api-key sk-... --temperature 0.7
llaminal --system-prompt "..."

# API key can also be set via env var
export LLAMINAL_API_KEY=sk-...

# No tests or linting configured yet
```

## Architecture

The source lives in `src/llaminal/` with entry point `cli.py:main()`.

**Core loop**: User input → `agent.py:run_agent_loop()` streams the LLM response → if tool calls are present, executes them via the tool registry, appends results to session history, and re-prompts the model. The loop exits when the model produces plain text with no tool calls.

**Key modules**:
- `cli.py` — Click CLI setup, prompt loop, Rich welcome banner with ASCII llama
- `agent.py` — Agentic loop: stream response, parse tool calls, execute, repeat. Handles Ctrl+C mid-stream, network errors, and malformed model output gracefully.
- `client.py` — `LlaminalClient` wraps httpx for async SSE streaming to `/v1/chat/completions`. Supports API key auth (Bearer token) and temperature. Skips malformed JSON chunks.
- `session.py` — Manages OpenAI-format message history; contains the default system prompt
- `render.py` — Rich-based terminal rendering (panels, markdown, streaming text)
- `tools/registry.py` — `Tool` dataclass + `ToolRegistry` for dispatch; converts tools to OpenAI function-calling schema. Returns error strings for unknown tools and tool exceptions (never raises).
- `tools/bash.py` — Shell execution with user confirmation, 30s timeout, structured output (stdout/stderr/exit_code/timed_out), shows working directory
- `tools/files.py` — `read_file` (100KB size cap, binary detection), `write_file` (diff preview on overwrite), `list_files` (200 result cap). All paths support `~` expansion.

**Patterns**:
- Fully async (`asyncio` + `httpx.AsyncClient`)
- Streaming-first: responses are printed token-by-token as SSE deltas arrive
- Destructive tools (bash, write_file) require user confirmation before execution
- Tools are registered as `Tool` dataclasses with JSON Schema parameters and async `execute` callables
- Error resilience: tool failures return error strings to model, network errors preserve session, Ctrl+C saves partial content

## PRD

The current MVP spec lives in `docs/prd/Llaminal_MVP_PRD_Revised.md`.
