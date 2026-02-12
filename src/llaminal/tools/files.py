"""File tools — read, write, and list files."""

import difflib
import glob as globmod
from pathlib import Path

from llaminal.tools.registry import Tool

MAX_FILE_SIZE = 100 * 1024  # 100KB
MAX_LIST_RESULTS = 200


async def _read_file(path: str) -> str:
    """Read and return the contents of a file."""
    try:
        p = Path(path).expanduser()

        if not p.exists():
            return f"Error: file not found: {path}"

        size = p.stat().st_size
        if size > MAX_FILE_SIZE:
            return f"Error: file is {size:,} bytes, exceeds {MAX_FILE_SIZE:,} byte limit"

        # Binary detection: read a sample and check for null bytes
        raw = p.read_bytes()
        if b"\x00" in raw[:8192]:
            return f"Error: file appears to be binary: {path}"

        return raw.decode(errors="replace")
    except Exception as e:
        return f"Error reading {path}: {e}"


async def _write_file(path: str, content: str) -> str:
    """Write content to a file after user confirmation."""
    try:
        p = Path(path).expanduser()

        print(f"\n  Write to: {path} ({len(content)} chars)")

        # Show diff preview when overwriting
        if p.exists():
            try:
                old_lines = p.read_text().splitlines(keepends=True)
                new_lines = content.splitlines(keepends=True)
                diff = difflib.unified_diff(old_lines, new_lines, fromfile="before", tofile="after")
                diff_text = "".join(diff)
                if diff_text:
                    print(f"  Diff preview:\n{diff_text}")
                else:
                    print("  (no changes)")
            except Exception:
                print("  (could not generate diff preview)")

        answer = input("  Proceed? [y/N] ").strip().lower()
        if answer != "y":
            return "Write cancelled by user."

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
        total = len(matches)

        if not matches:
            return f"No files matching '{pattern}'"

        if total > MAX_LIST_RESULTS:
            matches = matches[:MAX_LIST_RESULTS]
            return "\n".join(matches) + f"\n... ({total} total, showing first {MAX_LIST_RESULTS})"

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
