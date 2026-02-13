"""Rich-based rendering for assistant output, tool calls, and errors."""

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

console = Console()


class StreamRenderer:
    """Streams tokens via Rich Live, then finalizes as rendered Markdown."""

    def __init__(self) -> None:
        self._text = ""
        self._live = Live(
            Text(""),
            console=console,
            refresh_per_second=10,
            vertical_overflow="visible",
        )

    def start(self) -> None:
        self._live.start()

    def update(self, token: str) -> None:
        self._text += token
        self._live.update(Text(self._text))

    def finalize(self) -> None:
        """Replace streamed text with rendered Markdown, then stop."""
        if self._text.strip():
            self._live.update(Markdown(self._text))
        self._live.stop()

    def stop(self) -> None:
        """Stop without markdown render (for interruptions)."""
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
    args_text = "\n".join(f"  {k}: {v}" for k, v in args.items())
    content = Text.assemble(
        ("Tool: ", "bold cyan"),
        (name, "bold white"),
        ("\n",),
        (args_text, "dim"),
    )
    console.print(Panel(content, border_style="cyan", title="Tool Call", title_align="left"))


def render_tool_result(result: str) -> None:
    """Render tool output in a panel."""
    console.print(Panel(result, border_style="green", title="Result", title_align="left"))


def render_error(msg: str) -> None:
    """Render an error message in red."""
    console.print(f"[bold red]Error:[/bold red] {msg}")
