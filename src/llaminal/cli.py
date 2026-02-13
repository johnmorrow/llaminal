"""Entry point — input loop, Rich rendering, click CLI."""

import asyncio
from pathlib import Path

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from llaminal.agent import run_agent_loop
from llaminal.client import LlaminalClient
from llaminal.config import DEFAULTS, load_config, resolve
from llaminal.discover import discover_servers
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
@click.option("--port", default=None, type=int, help="Port of the local server (shorthand for --base-url http://localhost:<port>).")
@click.option("--base-url", default=None, help="Full base URL of the OpenAI-compatible server.")
@click.option("--model", default=None, help="Model name to send in requests.")
@click.option("--api-key", default=None, envvar="LLAMINAL_API_KEY", help="API key for authentication (or set LLAMINAL_API_KEY).")
@click.option("--temperature", default=None, type=float, help="Sampling temperature for the model.")
@click.option("--system-prompt", default=None, help="Override the default system prompt.")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True, path_type=Path), help="Path to config file (default: ~/.config/llaminal/config.toml).")
def main(
    port: int | None,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    temperature: float | None,
    system_prompt: str | None,
    config_path: Path | None,
) -> None:
    """Llaminal — an agentic CLI for local LLMs."""
    cfg = load_config(config_path)

    # Resolve each setting: CLI flag > env var (handled by Click for api_key) > config > default
    model = resolve(model, cfg.get("model"), DEFAULTS["model"])
    api_key = resolve(api_key, cfg.get("api_key"), DEFAULTS["api_key"])
    temperature = resolve(temperature, cfg.get("temperature"), DEFAULTS["temperature"])
    system_prompt = resolve(system_prompt, cfg.get("system_prompt"), DEFAULTS["system_prompt"])

    # Base URL resolution: --base-url > --port > config base_url > config port > auto-detect
    if base_url is None:
        if port is not None:
            base_url = f"http://localhost:{port}"
        else:
            base_url = resolve(None, cfg.get("base_url"), None)
            if base_url is None and cfg.get("port") is not None:
                base_url = f"http://localhost:{cfg['port']}"

    if base_url is None:
        # No explicit server configured — try auto-detection
        base_url = _auto_detect()

    if base_url is None:
        console.print("[bold red]Error:[/bold red] No LLM server found.")
        console.print("[dim]Start a server and retry, or specify one explicitly:\n")
        console.print("  llama-server -m model.gguf --port 8080")
        console.print("  llaminal --base-url http://localhost:8080")
        console.print("  llaminal --port 8080[/dim]")
        raise SystemExit(1)

    asyncio.run(_main_loop(base_url, model, api_key, temperature, system_prompt))


def _auto_detect() -> str | None:
    """Scan common ports for a running LLM server. Returns base_url or None."""
    console.print("[dim]Scanning for LLM servers...[/dim]")
    found = asyncio.run(discover_servers())

    if not found:
        return None

    if len(found) == 1:
        url, label = found[0]
        console.print(f"[dim]Found {label} at {url}[/dim]")
        return url

    # Multiple servers found — prompt user to choose
    console.print("[dim]Found multiple servers:[/dim]")
    for i, (url, label) in enumerate(found, 1):
        console.print(f"  [bold]{i}[/bold]) {label} — {url}")

    while True:
        try:
            choice = input(f"  Choose [1-{len(found)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(found):
                return found[idx][0]
        except (ValueError, EOFError, KeyboardInterrupt):
            return None


if __name__ == "__main__":
    main()
