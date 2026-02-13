"""PTY command executor — runs commands in the user's real shell via marker protocol."""

import asyncio
import os
import re
import sys


class PtyExecutor:
    """Executes commands by writing them into the PTY and capturing output via markers."""

    def __init__(self, shell_wrapper, scrollback):
        self._wrapper = shell_wrapper
        self._scrollback = scrollback
        self._counter = 0

    async def execute(self, command: str, timeout: float = 30.0) -> str:
        """Execute a command in the PTY and return its output.

        Shows a confirmation prompt, writes the command with a marker suffix
        into the PTY, waits for the marker in output, and returns captured text.
        """
        # Confirmation prompt (we're already in cooked mode during agent loop)
        cwd_info = ""
        try:
            from llaminal.cwd_tracker import CwdTracker
            tracker = CwdTracker(self._wrapper.child_pid)
            cwd = tracker.get_cwd()
            if cwd:
                cwd_info = f"\n  Working directory: {cwd}"
        except Exception:
            pass

        print(f"\n  Command: {command}{cwd_info}")
        answer = input("  Execute? [y/N] ").strip().lower()
        if answer != "y":
            return "Command execution cancelled by user."

        # Generate unique marker
        self._counter += 1
        marker_id = f"{os.getpid():x}{self._counter:x}"
        marker = f"___LLAMINAL_DONE_{marker_id}"
        marker_pattern = re.compile(
            rf"^{re.escape(marker)}_(\d+)___$", re.MULTILINE
        )

        # Build the command string with marker
        # Semicolon ensures marker runs even if command fails
        # $? captures the command's exit code (not printf's)
        cmd_str = f"{command}; printf '\\n{marker}_%d___\\n' $?\n"

        # Set up capture
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[tuple[str, int]] = loop.create_future()
        capture_buf: list[bytes] = []

        def capture_callback(data: bytes) -> None:
            capture_buf.append(data)
            # Check if marker has appeared in accumulated output
            accumulated = b"".join(capture_buf).decode("utf-8", errors="replace")
            match = marker_pattern.search(accumulated)
            if match and not result_future.done():
                exit_code = int(match.group(1))
                # Extract output between command echo and marker
                output = _extract_output(accumulated, command, marker, match)
                result_future.set_result((output, exit_code))

        # Register capture callback and enable PTY output display
        self._wrapper.add_master_output_callback(capture_callback)
        self._wrapper.set_show_pty_output(True)

        try:
            # Write command to PTY
            self._wrapper.write_to_shell(cmd_str.encode())

            # Wait for marker with timeout
            try:
                output, exit_code = await asyncio.wait_for(
                    result_future, timeout=timeout
                )
            except asyncio.TimeoutError:
                # Timeout — send Ctrl+C to interrupt
                self._wrapper.write_to_shell(b"\x03")
                await asyncio.sleep(0.2)  # brief pause for interrupt to process
                accumulated = b"".join(capture_buf).decode("utf-8", errors="replace")
                output = _extract_output_raw(accumulated, command)
                return _format_result(output, -1, timed_out=True, timeout_secs=timeout)

        finally:
            # Cleanup: disable PTY output, remove callback
            self._wrapper.set_show_pty_output(False)
            try:
                self._wrapper._on_master_output.remove(capture_callback)
            except ValueError:
                pass

        return _format_result(output, exit_code)


def _extract_output(
    accumulated: str, command: str, marker: str, match: re.Match
) -> str:
    """Extract command output between the echoed command and the marker."""
    # Find end of the echoed command line (first newline after command appears)
    cmd_end = accumulated.find("\n")
    if cmd_end == -1:
        cmd_end = 0
    else:
        cmd_end += 1

    # Output is everything from after the echo to before the marker line
    marker_start = match.start()
    # Walk back to the start of the marker line
    line_start = accumulated.rfind("\n", 0, marker_start)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1

    output = accumulated[cmd_end:line_start].strip()
    return output


def _extract_output_raw(accumulated: str, command: str) -> str:
    """Extract whatever output we have (for timeout case)."""
    cmd_end = accumulated.find("\n")
    if cmd_end == -1:
        return accumulated.strip()
    return accumulated[cmd_end + 1 :].strip()


def _format_result(
    output: str, exit_code: int, timed_out: bool = False, timeout_secs: float = 0
) -> str:
    """Format the result string for the agent."""
    # Cap output at 10KB (first 5KB + last 5KB)
    if len(output) > 10_000:
        output = output[:5_000] + "\n... (output truncated) ...\n" + output[-5_000:]

    parts = [f"stdout: {output}", f"exit_code: {exit_code}"]
    if timed_out:
        parts.append(f"timed_out: true")
        parts.append(f"Error: command timed out after {timeout_secs:.0f}s")
    else:
        parts.append("timed_out: false")
    return "\n".join(parts)
