# Llaminal MVP – Revised PRD (Aligned to Engineering Counterproposal)

**Author:** Product (with Engineering review)  
**Owner:** John Morrow  
**Date:** 2026-02-12  
**Status:** Implementation-ready (MVP)

---

## 1. Executive Summary

Llaminal is a CLI for chatting with a local (or remote) OpenAI-compatible model, with **agentic tool-calling** for shell + file operations.

**MVP goal:**

> A reliable, pleasant terminal chat experience that can safely execute a minimal set of tools, and that **does not crash** under malformed model output, tool errors, or network issues.

This PRD defines *only* what is required to ship MVP based on current code and real usage patterns.

---

## 2. Current State (Baseline)

The existing scaffold already includes:
- Streaming chat loop (token-by-token output)
- OpenAI-compatible endpoint connection (currently `http://localhost:<port>`)
- Session state with roles (system/user/assistant/tool)
- Tool registry + JSON schema tool-calling loop
- Tools: `bash`, `read_file`, `write_file`, `list_files`
- Confirmation prompts for `bash` and `write_file`
- Rich color-coded output
- CLI flags: `--port`, `--model`, `--system-prompt`
- Ctrl+D exit, Ctrl+C handling

**MVP work is hardening + flexibility, not a broad feature expansion.**

---

## 3. MVP Scope

### In-Scope (MVP)
1. **Tool hardening** (timeouts, size caps, binary detection, diff preview, result caps)
2. **Connection flexibility** (base URL + API key + temperature)
3. **Error resilience** (never crash; degrade gracefully)

### Out-of-Scope (Explicitly Deferred)
- YAML config file (`.llaminal.yaml`)
- `--cwd` / working directory switching (use `cd`)
- Directory traversal restrictions (confirmation is the security gate)
- Atomic writes (unless corruption observed)
- `max_tokens` configuration (server defaults)
- Plugin/tool ecosystem

---

## 4. User Experience Requirements

### 4.1 CLI Chat UX
**Requirements**
- Stream assistant output token-by-token
- Clean interruption:
  - Ctrl+C stops streaming request cleanly
  - Session history remains intact
- Clear formatting separation:
  - User messages
  - Assistant messages
  - Tool calls
  - Tool outputs
  - Errors
- Ctrl+D exits cleanly

**Success Criteria**
- A user can chat continuously for 30 minutes without a crash
- Interrupting mid-stream never corrupts the conversation state

---

## 5. Functional Requirements

## 5.1 Tool Calling Framework (Existing, Hardened)
The agent loop must:
- Provide tool schemas to the model
- Detect tool calls
- Execute tools sequentially (one-at-a-time), returning tool results to the model
- Never raise uncaught exceptions due to tool execution or model output

**Note:** Async implementation is acceptable; the observable behavior must be sequential and predictable.

---

## 5.2 Tools (MVP Requirements)

### 5.2.1 `bash`
**Purpose:** Execute shell commands.

**Behavior**
- Always prompt confirmation before execution
- Confirmation prompt must display:
  - Full command
  - Working directory
- Execute command with timeout (default **30s**, configurable)
- Capture stdout and stderr
- Return structured result including:
  - `stdout`
  - `stderr`
  - `exit_code`
  - `timed_out` (bool)

**Error Handling**
- On timeout: kill process, return structured timeout error
- On non-zero exit: return exit code + stderr; session continues

---

### 5.2.2 `read_file`
**Purpose:** Read text file contents.

**Behavior**
- Support absolute and relative paths (including `~` expansion)
- Enforce max file size (default **100KB**, configurable)
- Detect binary files (e.g., null-byte check) and refuse with a clear message
- Return file contents as text

**Error Handling**
- File not found / permission denied: return friendly error string; do not crash

---

### 5.2.3 `write_file`
**Purpose:** Create/overwrite text file.

**Behavior**
- Always prompt confirmation before writing
- When overwriting an existing file:
  - Show a **line diff preview** (basic unified diff acceptable)
- Write content (non-atomic is acceptable for MVP)

**Error Handling**
- Permission denied / invalid path: return friendly error string; do not crash

---

### 5.2.4 `list_files`
**Purpose:** List files using glob patterns.

**Behavior**
- Support glob/wildcards
- Cap results (default **200**)
- Output must be deterministic:
  - Sort by path
- Return paths only (no stat calls required for MVP)

**Error Handling**
- Invalid glob / permission issues: return friendly error string; do not crash

---

## 6. Connection Flexibility (MVP)

### 6.1 Base URL
Add:
- `--base-url` flag: full OpenAI-compatible base URL (e.g., `http://localhost:8080` or `http://127.0.0.1:11434/v1`)
- Keep `--port` as shorthand for `--base-url http://localhost:<port>`
  - If both supplied, `--base-url` wins

### 6.2 API Key
Add:
- `--api-key` flag
- `LLAMINAL_API_KEY` environment variable (env var used if flag not provided)

Client must send `Authorization: Bearer <key>` when api_key is present.

### 6.3 Temperature
Add:
- `--temperature` flag
Pass through to the OpenAI-compatible chat completion request.

---

## 7. Error Resilience (MVP)

The CLI must never crash ungracefully under these conditions:

### 7.1 Malformed Model Output
- Tool call JSON parse errors:
  - Catch error
  - Surface a warning in UI
  - Skip the bad chunk and continue (or request retry if needed)

### 7.2 Unknown Tool Calls
- If model requests an unknown tool:
  - Return a tool error result to the model: “Unknown tool: X”
  - Continue session

### 7.3 Network Failures
- If disconnect occurs mid-stream:
  - Display a clear error
  - Keep session state
  - Allow the user to retry with the next prompt

### 7.4 Ctrl+C Mid-stream
- Cancel the in-flight request cleanly
- Do not lose conversation history

### 7.5 Tool Failures
- Any tool exception is caught and returned to the model as an error string
- Never raise to top-level loop

---

## 8. Definition of Done (MVP)

MVP is complete when all are true:

1. **Streaming chat** works reliably; Ctrl+C cancels cleanly; session survives
2. **All 4 tools** have safety limits:
   - bash timeout + exit_code
   - read_file size cap + binary detection
   - write_file diff preview on overwrite
   - list_files capped + sorted
3. **No unhandled exceptions** from:
   - malformed model output
   - unknown tool calls
   - tool execution errors
   - network disconnects
4. **Connects to any OpenAI-compatible endpoint** with `--base-url`
5. **API key auth** works via flag or env var
6. Verified against:
   - llama.cpp server
   - Ollama
   - any OpenAI-compatible endpoint

---

## 9. Implementation Plan (Phased)

### Phase 1 — Tool Hardening (Highest Impact)
- bash: timeout + exit_code + show cwd in confirmation
- read_file: 100KB cap + binary detection + `~` expansion
- write_file: diff preview on overwrite
- list_files: cap 200 + sorted output

### Phase 2 — Connection Flexibility
- Add `--base-url`
- Keep `--port` as shorthand
- Add `--api-key` + `LLAMINAL_API_KEY`
- Add `--temperature`

### Phase 3 — Error Resilience
- Harden parsing + unknown tool behavior
- Network mid-stream handling
- Ctrl+C cancellation correctness
- Tool exceptions always returned, never raised

---

## 10. Post-MVP (Explicitly Deferred)
- `.llaminal.yaml` config file and merge precedence logic
- `--cwd` / working_directory support
- Directory traversal restrictions
- Atomic writes
- `max_tokens` tuning
- Plugin architecture / tool ecosystem

---
