"""Bash tool — run shell commands with user confirmation."""

import asyncio

from llaminal.tools.registry import Tool


async def _run_bash(command: str) -> str:
    """Execute a shell command after user confirmation."""
    print(f"\n  Command: {command}")
    answer = input("  Execute? [y/N] ").strip().lower()
    if answer != "y":
        return "Command execution cancelled by user."

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    output = ""
    if stdout:
        output += stdout.decode(errors="replace")
    if stderr:
        output += ("\n--- stderr ---\n" if output else "") + stderr.decode(errors="replace")

    if not output:
        output = f"(process exited with code {proc.returncode})"

    # Cap output length
    if len(output) > 10_000:
        output = output[:10_000] + "\n... (truncated)"

    return output


bash_tool = Tool(
    name="bash",
    description="Run a shell command and return its output. Use for system commands, installations, builds, etc.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
        },
        "required": ["command"],
    },
    execute=_run_bash,
)
