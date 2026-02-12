"""Chat history and message management."""

SYSTEM_PROMPT = """\
You are Llaminal, a helpful AI assistant running in a terminal. You have access to tools \
that let you interact with the user's system. Use them when the user asks you to perform \
tasks like reading files, writing files, listing directories, or running shell commands.

When you need to use a tool, emit a tool call. You can chain multiple tool calls in \
sequence to accomplish complex tasks. Always explain what you're about to do before \
calling a tool.

Be concise and direct in your responses.\
"""


class Session:
    """Manages the conversation message history in OpenAI message format."""

    def __init__(self, system_prompt: str | None = None):
        self.messages: list[dict] = [
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT}
        ]

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_assistant_tool_calls(self, content: str | None, tool_calls: list[dict]) -> None:
        """Append an assistant message that includes tool_calls."""
        msg: dict = {"role": "assistant", "tool_calls": tool_calls}
        if content:
            msg["content"] = content
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def get_messages(self) -> list[dict]:
        return self.messages
