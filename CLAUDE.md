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
llaminal --port 8080 --model local-model --system-prompt "..."

# No tests or linting configured yet
```

## Architecture

The source lives in `src/llaminal/` with entry point `cli.py:main()`.

**Core loop**: User input → `agent.py:run_agent_loop()` streams the LLM response → if tool calls are present, executes them via the tool registry, appends results to session history, and re-prompts the model. The loop exits when the model produces plain text with no tool calls.

**Key modules**:
- `cli.py` — Click CLI setup, prompt loop, Rich welcome panel
- `agent.py` — Agentic loop: stream response, parse tool calls, execute, repeat
- `client.py` — `LlaminalClient` wraps httpx for async SSE streaming to `/v1/chat/completions`
- `session.py` — Manages OpenAI-format message history; contains the default system prompt
- `render.py` — Rich-based terminal rendering (panels, markdown, streaming text)
- `tools/registry.py` — `Tool` dataclass + `ToolRegistry` for dispatch; converts tools to OpenAI function-calling schema
- `tools/bash.py` — Shell execution with user confirmation, output capped at 10k chars
- `tools/files.py` — `read_file`, `write_file`, `list_files` tools

**Patterns**:
- Fully async (`asyncio` + `httpx.AsyncClient`)
- Streaming-first: responses are printed token-by-token as SSE deltas arrive
- Destructive tools (bash, write_file) require user confirmation before execution
- Tools are registered as `Tool` dataclasses with JSON Schema parameters and async `execute` callables
