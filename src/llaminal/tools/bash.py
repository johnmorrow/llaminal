"""Bash tool — run shell commands with user confirmation."""

import asyncio
import os

from llaminal.tools.registry import Tool

DEFAULT_TIMEOUT = 30


async def _run_bash(command: str) -> str:
    """Execute a shell command after user confirmation."""
    cwd = os.getcwd()
    print(f"\n  Command: {command}")
    print(f"  Working directory: {cwd}")
    answer = input("  Execute? [y/N] ").strip().lower()
    if answer != "y":
        return "Command execution cancelled by user."

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=DEFAULT_TIMEOUT
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return (
            f"stdout: \n"
            f"stderr: \n"
            f"exit_code: -1\n"
            f"timed_out: true\n"
            f"Error: command timed out after {DEFAULT_TIMEOUT}s"
        )

    stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
    stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""

    # Cap output length
    if len(stdout) > 10_000:
        stdout = stdout[:10_000] + "\n... (truncated)"
    if len(stderr) > 10_000:
        stderr = stderr[:10_000] + "\n... (truncated)"

    return (
        f"stdout: {stdout}\n"
        f"stderr: {stderr}\n"
        f"exit_code: {proc.returncode}\n"
        f"timed_out: false"
    )


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
