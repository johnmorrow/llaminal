"""Agentic loop — stream response, execute tool calls, re-prompt."""

import json

import httpx

from llaminal.client import LlaminalClient
from llaminal.render import render_error, render_tool_call, render_tool_result
from llaminal.session import Session
from llaminal.tools.registry import ToolRegistry


async def run_agent_loop(
    client: LlaminalClient,
    session: Session,
    registry: ToolRegistry,
) -> None:
    """Run the agent loop until the model produces a plain text response (no tool calls)."""
    while True:
        content_parts: list[str] = []
        tool_calls_by_index: dict[int, dict] = {}

        try:
            async for delta in client.stream_chat(
                session.get_messages(),
                tools=registry.to_openai_schema() or None,
            ):
                # Accumulate content tokens
                if delta.content:
                    content_parts.append(delta.content)
                    # Stream tokens to terminal
                    print(delta.content, end="", flush=True)

                # Accumulate tool call deltas
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta["index"]
                        if idx not in tool_calls_by_index:
                            tool_calls_by_index[idx] = {
                                "id": tc_delta.get("id", f"call_{idx}"),
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        tc = tool_calls_by_index[idx]
                        fn = tc_delta.get("function", {})
                        if "name" in fn:
                            tc["function"]["name"] += fn["name"]
                        if "arguments" in fn:
                            tc["function"]["arguments"] += fn["arguments"]

        except KeyboardInterrupt:
            # Ctrl+C mid-stream: save what we have, don't corrupt session
            full_content = "".join(content_parts)
            if full_content:
                print()
                session.add_assistant(full_content)
            raise

        except httpx.ConnectError:
            print()
            render_error(
                f"Could not connect to {client.base_url}.\n"
                "  Is your LLM server running? Try:\n"
                "    llama-server -m model.gguf --port 8080"
            )
            _pop_last_user_message(session)
            return

        except httpx.TimeoutException:
            print()
            render_error(
                "Request timed out. The model may be loading or the server may be overloaded.\n"
                "  Try again in a moment."
            )
            _pop_last_user_message(session)
            return

        except (httpx.RemoteProtocolError, httpx.ReadError):
            print()
            render_error(
                "Connection was interrupted. The server may have closed unexpectedly.\n"
                "  Check that your server is still running and try again."
            )
            _pop_last_user_message(session)
            return

        except httpx.HTTPStatusError as e:
            print()
            code = e.response.status_code
            if code in (401, 403):
                render_error(
                    f"Authentication failed (HTTP {code}).\n"
                    "  Check your --api-key or LLAMINAL_API_KEY environment variable."
                )
            elif code == 404:
                render_error(
                    f"Endpoint not found (HTTP 404) at {client.base_url}.\n"
                    "  Is this an OpenAI-compatible server? Check your --base-url."
                )
            elif code >= 500:
                render_error(
                    f"Server error (HTTP {code}). The LLM server may be overloaded or misconfigured.\n"
                    f"  {e.response.text[:200]}"
                )
            else:
                render_error(f"Server returned HTTP {code}: {e.response.text[:200]}")
            return

        except Exception as e:
            print()
            render_error(f"Unexpected error: {e}")
            return

        full_content = "".join(content_parts)
        tool_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]

        # End streaming line
        if full_content:
            print()

        if not tool_calls:
            # Plain text response — turn is complete
            if full_content:
                session.add_assistant(full_content)
            return

        # We have tool calls — record them and execute
        session.add_assistant_tool_calls(full_content or None, tool_calls)

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
            except json.JSONDecodeError:
                fn_args = {}

            render_tool_call(fn_name, fn_args)
            result = await registry.execute(fn_name, fn_args)
            render_tool_result(result)
            session.add_tool_result(tc["id"], result)

        # Loop back to re-prompt the model with tool results


def _pop_last_user_message(session: Session) -> None:
    """Remove the last user message so the user can retry after a failure."""
    if session.messages and session.messages[-1]["role"] == "user":
        session.messages.pop()
