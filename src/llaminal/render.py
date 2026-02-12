"""Rich-based rendering for assistant output, tool calls, and errors."""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

console = Console()


def render_assistant(text: str) -> None:
    """Render assistant response as markdown."""
    if not text.strip():
        return
    md = Markdown(text)
    console.print(md)


def render_tool_call(name: str, args: dict) -> None:
    """Render a styled tool invocation block."""
    args_text = "\n".join(f"  {k}: {v}" for k, v in args.items())
    content = Text.assemble(
        (f"Tool: ", "bold cyan"),
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
