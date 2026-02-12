"""Agentic loop — stream response, execute tool calls, re-prompt."""

import json

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

        except Exception as e:
            render_error(str(e))
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
