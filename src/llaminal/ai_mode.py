"""AI mode — handles input, rendering, and agent loop when AI mode is active."""

import asyncio
import os
import sys
import termios
import tty

from rich.console import Console
from rich.text import Text

from llaminal.agent import run_agent_loop
from llaminal.client import LlaminalClient
from llaminal.render import render_error
from llaminal.session import Session
from llaminal.storage import Storage
from llaminal.themes import get_theme
from llaminal.tools.registry import ToolRegistry

console = Console()

PROMPT_TEXT = "\U0001f999> "  # 🦙>

# Terminal title OSC sequences
_TITLE_AI_MODE = b"\x1b]0;llaminal \xf0\x9f\xa6\x99 AI Mode\x07"  # 🦙
_TITLE_RESET = b"\x1b]0;\x07"


def _styled_prompt_bytes() -> bytes:
    """Render the prompt with theme color as ANSI escape bytes."""
    theme = get_theme()
    t = Text(PROMPT_TEXT, style=theme.ai_prompt)
    ansi_console = Console(force_terminal=True)
    with ansi_console.capture() as capture:
        ansi_console.print(t, end="")
    return capture.get().encode("utf-8")


class AIMode:
    """Manages AI mode: input collection, agent loop execution, and display."""

    def __init__(
        self,
        shell_wrapper,
        client: LlaminalClient | None,
        session: Session,
        registry: ToolRegistry,
        storage: Storage,
        session_id: str,
        show_stats: bool = False,
        context_provider=None,
        cwd_provider=None,
    ):
        self._shell = shell_wrapper
        self._client = client
        self._session = session
        self._registry = registry
        self._storage = storage
        self._session_id = session_id
        self._show_stats = show_stats
        self._context_provider = context_provider
        self._cwd_provider = cwd_provider

        self._buffer = bytearray()
        self._cursor_pos = 0
        self._active = False
        self._save_index = len(session.messages)
        self._running_agent = False
        self._pty_executing = False

    @property
    def active(self) -> bool:
        return self._active

    def enter(self) -> None:
        """Enter AI mode — display prompt, start capturing input."""
        self._active = True
        self._buffer.clear()
        self._cursor_pos = 0

        # Inject shell context and cwd if available
        context = self._context_provider() if self._context_provider else None
        cwd = self._cwd_provider() if self._cwd_provider else None
        if context or cwd:
            self._session.set_shell_context(context or "", cwd=cwd)

        # Set terminal title and show prompt
        self._write_output(_TITLE_AI_MODE)
        self._write_output(b"\r\n")
        self._write_output(_styled_prompt_bytes())

    def exit(self) -> None:
        """Exit AI mode — return to shell."""
        self._active = False
        self._buffer.clear()
        self._cursor_pos = 0
        self._shell.exit_ai_mode()
        self._write_output(_TITLE_RESET)
        self._write_output(b"\r\n")

    def enter_fix_it(self) -> None:
        """ESC-ESC-f shortcut: enter AI mode and auto-submit a fix-it query."""
        self._enter_with_auto_query(
            "The last command failed. Explain the error and suggest how to fix it.",
            "[fix-it] Analyzing...",
        )

    def enter_explain_it(self) -> None:
        """ESC-ESC-e shortcut: enter AI mode and auto-submit an explain query."""
        self._enter_with_auto_query(
            "Explain the output of the last command.",
            "[explain] Analyzing...",
        )

    def _enter_with_auto_query(self, query: str, status_msg: str) -> None:
        """Enter AI mode and immediately submit a query."""
        self._active = True
        self._buffer.clear()
        self._cursor_pos = 0
        self._shell.ai_mode = True

        # Inject shell context and cwd
        context = self._context_provider() if self._context_provider else None
        cwd = self._cwd_provider() if self._cwd_provider else None
        if context or cwd:
            self._session.set_shell_context(context or "", cwd=cwd)

        # Show status
        self._write_output(b"\r\n")
        self._write_output(f"\x1b[33m{status_msg}\x1b[0m\r\n".encode())

        # Auto-submit the query
        asyncio.get_running_loop().create_task(self._run_query(query))

    def handle_input(self, data: bytes) -> None:
        """Process raw input bytes while in AI mode."""
        if self._running_agent:
            # During agent execution, only handle Ctrl+C
            if b"\x03" in data:
                if self._pty_executing:
                    # Forward Ctrl+C to PTY during tool execution
                    self._shell.write_to_shell(b"\x03")
                # else: KeyboardInterrupt is handled by the agent loop
            return

        i = 0
        while i < len(data):
            b = data[i]
            i += 1

            if b == 0x1B:  # ESC
                # Check for escape sequence (arrow keys, etc.)
                if i < len(data) and data[i] == 0x5B:  # ESC [
                    i += 1
                    if i < len(data):
                        code = data[i]
                        i += 1
                        if code == 0x44:  # Left arrow
                            self._move_cursor_left()
                        elif code == 0x43:  # Right arrow
                            self._move_cursor_right()
                        elif code == 0x48:  # Home
                            self._move_cursor_home()
                        elif code == 0x46:  # End
                            self._move_cursor_end()
                        # Ignore other escape sequences
                else:
                    # Single ESC — exit AI mode
                    self.exit()
                    return

            elif b == 0x0D:  # Enter
                line = self._buffer.decode("utf-8", errors="replace").strip()
                self._write_output(b"\r\n")
                if line:
                    asyncio.get_running_loop().create_task(self._run_query(line))
                else:
                    # Empty enter — just redraw prompt
                    self._write_output(_styled_prompt_bytes())
                self._buffer.clear()
                self._cursor_pos = 0

            elif b == 0x7F or b == 0x08:  # Backspace
                if self._cursor_pos > 0:
                    del self._buffer[self._cursor_pos - 1]
                    self._cursor_pos -= 1
                    self._redraw_line()

            elif b == 0x03:  # Ctrl+C
                self._buffer.clear()
                self._cursor_pos = 0
                self._write_output(b"^C\r\n")
                self._write_output(_styled_prompt_bytes())

            elif b == 0x04:  # Ctrl+D
                if not self._buffer:
                    self.exit()
                    return

            elif b == 0x01:  # Ctrl+A (Home)
                self._move_cursor_home()

            elif b == 0x05:  # Ctrl+E (End)
                self._move_cursor_end()

            elif b == 0x15:  # Ctrl+U (kill line)
                self._buffer.clear()
                self._cursor_pos = 0
                self._redraw_line()

            elif b >= 0x20:  # Printable characters
                self._buffer.insert(self._cursor_pos, b)
                self._cursor_pos += 1
                self._redraw_line()

    def _move_cursor_left(self) -> None:
        if self._cursor_pos > 0:
            self._cursor_pos -= 1
            self._write_output(b"\x1b[D")

    def _move_cursor_right(self) -> None:
        if self._cursor_pos < len(self._buffer):
            self._cursor_pos += 1
            self._write_output(b"\x1b[C")

    def _move_cursor_home(self) -> None:
        if self._cursor_pos > 0:
            self._write_output(f"\x1b[{self._cursor_pos}D".encode())
            self._cursor_pos = 0

    def _move_cursor_end(self) -> None:
        remaining = len(self._buffer) - self._cursor_pos
        if remaining > 0:
            self._write_output(f"\x1b[{remaining}C".encode())
            self._cursor_pos = len(self._buffer)

    def _redraw_line(self) -> None:
        """Redraw the current input line."""
        self._write_output(b"\r")
        self._write_output(b"\x1b[K")  # Clear line
        self._write_output(_styled_prompt_bytes())
        text = self._buffer.decode("utf-8", errors="replace")
        self._write_output(text.encode("utf-8"))
        # Move cursor to correct position
        chars_after = len(self._buffer) - self._cursor_pos
        if chars_after > 0:
            self._write_output(f"\x1b[{chars_after}D".encode())

    def _write_output(self, data: bytes) -> None:
        """Write bytes directly to stdout."""
        try:
            os.write(sys.stdout.fileno(), data)
        except OSError:
            pass

    async def _run_query(self, text: str) -> None:
        """Send user text to the agent loop and stream the response."""
        if not self._client:
            self._write_output(
                b"\x1b[33mNo model server found. Run `ollama serve` or "
                b"`llama-server` to enable AI.\x1b[0m\r\n"
            )
            self._write_output(_styled_prompt_bytes())
            return

        self._running_agent = True

        # Restore terminal to cooked mode for Rich rendering
        self._shell_to_cooked()

        try:
            self._session.add_user(text)
            console.print()
            await run_agent_loop(
                self._client, self._session, self._registry,
                show_stats=self._show_stats,
            )
            # Persist messages
            self._storage.save_messages(
                self._session_id, self._session.messages, self._save_index
            )
            self._save_index = len(self._session.messages)
            console.print()
        except KeyboardInterrupt:
            console.print("\n[yellow]Generation cancelled.[/yellow]")
        except Exception as e:
            render_error(f"Unexpected error: {e}")
        finally:
            # Return to raw mode for PTY proxying
            self._shell_to_raw()
            self._running_agent = False
            self._write_output(_styled_prompt_bytes())

    def _shell_to_cooked(self) -> None:
        """Temporarily restore terminal to cooked mode for Rich output."""
        if self._shell._original_termios is not None:
            try:
                termios.tcsetattr(
                    sys.stdin.fileno(),
                    termios.TCSADRAIN,
                    self._shell._original_termios,
                )
            except (termios.error, OSError):
                pass

    def _shell_to_raw(self) -> None:
        """Return terminal to raw mode for PTY proxying."""
        try:
            tty.setraw(sys.stdin.fileno())
        except (termios.error, OSError):
            pass
