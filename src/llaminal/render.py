"""Rich-based rendering for assistant output, tool calls, and errors."""

import threading
import time

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from llaminal.themes import get_theme

console = Console()

LLAMA = "\U0001f999"  # 🦙
DOT_TRAIL = "·" * 20


class StreamRenderer:
    """Streams tokens via Rich Live, with a llama thinking animation before first token."""

    def __init__(self, show_stats: bool = False) -> None:
        self._text = ""
        self._token_count = 0
        self._first_token = False
        self._show_stats = show_stats
        self._start_time: float = 0.0
        self._first_token_time: float = 0.0
        self._live = Live(
            Text(""),
            console=console,
            refresh_per_second=10,
            vertical_overflow="visible",
        )
        self._thinking_stop = threading.Event()
        self._thinking_thread: threading.Thread | None = None

    def start(self) -> None:
        self._start_time = time.monotonic()
        self._live.start()
        self._thinking_stop.clear()
        self._thinking_thread = threading.Thread(target=self._animate_thinking, daemon=True)
        self._thinking_thread.start()

    def _animate_thinking(self) -> None:
        """Animate the llama eating dots until first token or stop."""
        trail = DOT_TRAIL
        while not self._thinking_stop.is_set():
            for i in range(len(trail) + 1):
                if self._thinking_stop.is_set():
                    return
                frame = f"  {' ' * i}{LLAMA}{trail[i:]}"
                self._live.update(Text(frame, style="dim"))
                time.sleep(0.12)

    def _stop_thinking(self) -> None:
        """Stop the thinking animation."""
        if self._thinking_thread and self._thinking_thread.is_alive():
            self._thinking_stop.set()
            self._thinking_thread.join(timeout=0.5)
            self._thinking_thread = None

    def update(self, token: str) -> None:
        if not self._first_token:
            self._stop_thinking()
            self._first_token = True
            self._first_token_time = time.monotonic()
        self._text += token
        self._token_count += 1
        self._live.update(Text(self._text))

    def finalize(self) -> None:
        """Replace streamed text with rendered Markdown, then stop."""
        self._stop_thinking()
        if self._text.strip():
            self._live.update(Markdown(self._text))
        self._live.stop()
        self._print_stats()

    def _print_stats(self) -> None:
        if not self._show_stats or not self._first_token:
            return
        now = time.monotonic()
        total = now - self._start_time
        ttft = self._first_token_time - self._start_time
        tps = self._token_count / (now - self._first_token_time) if now > self._first_token_time else 0
        console.print(
            f"[dim]{self._token_count} tokens · {total:.1f}s · {tps:.1f} tok/s · {ttft:.1f}s to first token[/dim]"
        )

    def stop(self) -> None:
        """Stop without markdown render (for interruptions)."""
        self._stop_thinking()
        self._live.stop()

    def get_text(self) -> str:
        return self._text


def render_assistant(text: str) -> None:
    """Render assistant response as markdown."""
    if not text.strip():
        return
    console.print(Markdown(text))


def render_tool_call(name: str, args: dict) -> None:
    """Render a styled tool invocation block."""
    theme = get_theme()
    args_text = "\n".join(f"  {k}: {v}" for k, v in args.items())
    content = Text.assemble(
        ("Tool: ", theme.tool_label),
        (name, theme.tool_name),
        ("\n",),
        (args_text, "dim"),
    )
    console.print(Panel(content, border_style=theme.tool_border, title="Tool Call", title_align="left"))


def render_tool_result(result: str) -> None:
    """Render tool output in a panel."""
    theme = get_theme()
    console.print(Panel(result, border_style=theme.result_border, title="Result", title_align="left"))


def render_error(msg: str) -> None:
    """Render an error message in red."""
    theme = get_theme()
    console.print(f"[{theme.error}]Error:[/{theme.error}] {msg}")
