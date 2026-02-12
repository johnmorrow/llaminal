"""File tools — read, write, and list files."""

import glob as globmod
from pathlib import Path

from llaminal.tools.registry import Tool


async def _read_file(path: str) -> str:
    """Read and return the contents of a file."""
    try:
        return Path(path).expanduser().read_text()
    except Exception as e:
        return f"Error reading {path}: {e}"


async def _write_file(path: str, content: str) -> str:
    """Write content to a file after user confirmation."""
    print(f"\n  Write to: {path} ({len(content)} chars)")
    answer = input("  Proceed? [y/N] ").strip().lower()
    if answer != "y":
        return "Write cancelled by user."

    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


async def _list_files(pattern: str) -> str:
    """List files matching a glob pattern."""
    try:
        expanded = str(Path(pattern).expanduser())
        matches = sorted(globmod.glob(expanded, recursive=True))
        if not matches:
            return f"No files matching '{pattern}'"
        return "\n".join(matches)
    except Exception as e:
        return f"Error listing files: {e}"


read_file_tool = Tool(
    name="read_file",
    description="Read the contents of a file at the given path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read",
            },
        },
        "required": ["path"],
    },
    execute=_read_file,
)

write_file_tool = Tool(
    name="write_file",
    description="Write content to a file at the given path. Creates parent directories if needed.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["path", "content"],
    },
    execute=_write_file,
)

list_files_tool = Tool(
    name="list_files",
    description="List files matching a glob pattern (supports ** for recursive matching).",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match files (e.g. 'src/**/*.py')",
            },
        },
        "required": ["pattern"],
    },
    execute=_list_files,
)
