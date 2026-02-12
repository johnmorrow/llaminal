"""Entry point — input loop, Rich rendering, click CLI."""

import asyncio

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from llaminal.agent import run_agent_loop
from llaminal.client import LlaminalClient
from llaminal.session import Session
from llaminal.tools.bash import bash_tool
from llaminal.tools.files import list_files_tool, read_file_tool, write_file_tool
from llaminal.tools.registry import ToolRegistry


console = Console()


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(bash_tool)
    registry.register(read_file_tool)
    registry.register(write_file_tool)
    registry.register(list_files_tool)
    return registry


async def _main_loop(port: int, model: str, system_prompt: str | None) -> None:
    base_url = f"http://localhost:{port}"
    client = LlaminalClient(base_url=base_url, model=model)
    session = Session(system_prompt=system_prompt)
    registry = build_registry()

    # Welcome banner
    title = Text.assemble(
        ("Llaminal", "bold magenta"),
        (" v0.1.0", "dim"),
    )
    console.print(Panel(title, subtitle=f"connected to {base_url}", border_style="magenta"))
    console.print("[dim]Type a message to chat. Ctrl+C to cancel, Ctrl+D to exit.[/dim]\n")

    prompt_session: PromptSession = PromptSession(history=InMemoryHistory())

    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: prompt_session.prompt("you> ")
            )
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break
        except KeyboardInterrupt:
            continue

        user_input = user_input.strip()
        if not user_input:
            continue

        session.add_user(user_input)
        console.print()

        try:
            await run_agent_loop(client, session, registry)
        except KeyboardInterrupt:
            console.print("\n[yellow]Generation cancelled.[/yellow]")

        console.print()

    await client.close()


@click.command()
@click.option("--port", default=8080, help="Port of the OpenAI-compatible server.")
@click.option("--model", default="local-model", help="Model name to send in requests.")
@click.option("--system-prompt", default=None, help="Override the default system prompt.")
def main(port: int, model: str, system_prompt: str | None) -> None:
    """Llaminal — an agentic CLI for local LLMs."""
    asyncio.run(_main_loop(port, model, system_prompt))


if __name__ == "__main__":
    main()
