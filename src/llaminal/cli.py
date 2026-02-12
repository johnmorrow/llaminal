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


async def _main_loop(
    base_url: str,
    model: str,
    api_key: str | None,
    temperature: float | None,
    system_prompt: str | None,
) -> None:
    client = LlaminalClient(
        base_url=base_url, model=model, api_key=api_key, temperature=temperature
    )
    session = Session(system_prompt=system_prompt)
    registry = build_registry()

    # Welcome banner
    brown = "rgb(160,100,50)"
    banner = Text()
    banner.append("  @@@@@", style=brown)
    banner.append("     Llaminal", style="bold magenta")
    banner.append(" v0.1.0\n", style="dim")
    banner.append(" @(", style=brown)
    banner.append("o o", style="bold black")
    banner.append(")@", style=brown)
    banner.append(f"    {base_url}\n", style="dim")
    banner.append("  (   )~", style=brown)
    banner.append("\n")
    banner.append("   ||||", style=brown)
    banner.append("      Type a message to chat. Ctrl+C to cancel, Ctrl+D to exit.\n", style="dim italic")
    console.print(Panel(banner, border_style="magenta", padding=(0, 1)))

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
@click.option("--port", default=8080, help="Port of the local server (shorthand for --base-url http://localhost:<port>).")
@click.option("--base-url", default=None, help="Full base URL of the OpenAI-compatible server.")
@click.option("--model", default="local-model", help="Model name to send in requests.")
@click.option("--api-key", default=None, envvar="LLAMINAL_API_KEY", help="API key for authentication (or set LLAMINAL_API_KEY).")
@click.option("--temperature", default=None, type=float, help="Sampling temperature for the model.")
@click.option("--system-prompt", default=None, help="Override the default system prompt.")
def main(
    port: int,
    base_url: str | None,
    model: str,
    api_key: str | None,
    temperature: float | None,
    system_prompt: str | None,
) -> None:
    """Llaminal — an agentic CLI for local LLMs."""
    # --base-url wins over --port
    if base_url is None:
        base_url = f"http://localhost:{port}"

    asyncio.run(_main_loop(base_url, model, api_key, temperature, system_prompt))


if __name__ == "__main__":
    main()
