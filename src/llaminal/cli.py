"""Entry point — input loop, Rich rendering, click CLI."""

import asyncio
import time
from pathlib import Path

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.table import Table

from llaminal.agent import run_agent_loop
from llaminal.banners import print_banner
from llaminal.client import LlaminalClient
from llaminal.config import DEFAULTS, load_config, resolve
from llaminal.discover import discover_servers
from llaminal.moods import MOOD_NAMES, MOODS
from llaminal.session import Session
from llaminal.storage import Storage
from llaminal.themes import THEME_NAMES, THEMES, set_theme
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
    resume_id: str | None,
    show_stats: bool = False,
    sound: bool = False,
    quiet: bool = False,
) -> None:
    client = LlaminalClient(
        base_url=base_url, model=model, api_key=api_key, temperature=temperature
    )
    storage = Storage()
    registry = build_registry()

    # Resume existing session or start new one
    if resume_id:
        messages = storage.load_session(resume_id)
        if not messages:
            console.print(f"[bold red]Error:[/bold red] Session '{resume_id}' not found.")
            await client.close()
            storage.close()
            return
        session = Session(system_prompt=system_prompt)
        session.messages = messages
        session_id = resume_id
        save_index = len(messages)
        console.print(f"[dim]Resumed session {session_id}[/dim]\n")
    else:
        session = Session(system_prompt=system_prompt)
        session_id = storage.create_session(model)
        # Save the system prompt message
        storage.save_messages(session_id, session.messages, 0)
        save_index = len(session.messages)

    # Welcome banner
    if not quiet:
        print_banner(console, base_url)

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

        t0 = time.monotonic()
        try:
            await run_agent_loop(client, session, registry, show_stats=show_stats)
        except KeyboardInterrupt:
            console.print("\n[yellow]Generation cancelled.[/yellow]")

        if sound and (time.monotonic() - t0) > 3.0:
            print("\a", end="", flush=True)

        # Persist new messages
        storage.save_messages(session_id, session.messages, save_index)
        save_index = len(session.messages)

        console.print()

    await client.close()
    storage.close()


def _show_history() -> None:
    """Display recent conversation sessions."""
    storage = Storage()
    sessions = storage.list_sessions()
    storage.close()

    if not sessions:
        console.print("[dim]No conversation history yet.[/dim]")
        return

    table = Table(title="Recent Sessions", border_style="dim")
    table.add_column("ID", style="bold")
    table.add_column("Title")
    table.add_column("Model", style="dim")
    table.add_column("Messages", justify="right")
    table.add_column("Date", style="dim")

    for s in sessions:
        date = s["created_at"][:10]
        table.add_row(s["id"], s["title"], s["model"], str(s["message_count"]), date)

    console.print(table)
    console.print("\n[dim]Resume a session with: llaminal --resume <ID>[/dim]")


@click.command()
@click.option("--port", default=None, type=int, help="Port of the local server (shorthand for --base-url http://localhost:<port>).")
@click.option("--base-url", default=None, help="Full base URL of the OpenAI-compatible server.")
@click.option("--model", default=None, help="Model name to send in requests.")
@click.option("--api-key", default=None, envvar="LLAMINAL_API_KEY", help="API key for authentication (or set LLAMINAL_API_KEY).")
@click.option("--temperature", default=None, type=float, help="Sampling temperature for the model.")
@click.option("--system-prompt", default=None, help="Override the default system prompt.")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True, path_type=Path), help="Path to config file (default: ~/.config/llaminal/config.toml).")
@click.option("--resume", "resume_id", default=None, help="Resume a previous session (ID, or 'last' for most recent).")
@click.option("--history", "show_history", is_flag=True, help="Show recent conversation sessions.")
@click.option("--stats", "show_stats", is_flag=True, help="Show token/sec and latency stats after each response.")
@click.option("--mood", default=None, type=click.Choice(MOOD_NAMES, case_sensitive=False), help="Use a persona preset (e.g. pirate, poet, senior-engineer).")
@click.option("--sound", is_flag=True, help="Play a terminal bell when a long response finishes.")
@click.option("--quiet", "-q", is_flag=True, help="Suppress the startup banner.")
@click.option("--theme", default=None, type=click.Choice(THEME_NAMES, case_sensitive=False), help="Color theme (default, light, solarized, dracula, catppuccin, llama).")
def main(
    port: int | None,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    temperature: float | None,
    system_prompt: str | None,
    config_path: Path | None,
    resume_id: str | None,
    show_history: bool,
    show_stats: bool,
    mood: str | None,
    sound: bool,
    quiet: bool,
    theme: str | None,
) -> None:
    """Llaminal — an agentic CLI for local LLMs."""
    if show_history:
        _show_history()
        return

    cfg = load_config(config_path)

    # Set color theme early so all rendering uses it
    theme_name = resolve(theme, cfg.get("theme"), "default")
    if theme_name not in THEMES:
        console.print(f"[bold red]Error:[/bold red] Unknown theme '{theme_name}'. Options: {', '.join(THEME_NAMES)}")
        raise SystemExit(1)
    set_theme(theme_name)

    # Resolve each setting: CLI flag > env var (handled by Click for api_key) > config > default
    model = resolve(model, cfg.get("model"), DEFAULTS["model"])
    api_key = resolve(api_key, cfg.get("api_key"), DEFAULTS["api_key"])
    temperature = resolve(temperature, cfg.get("temperature"), DEFAULTS["temperature"])
    # Mood resolution: --system-prompt > --mood > config mood > config system_prompt > default
    if mood is None:
        mood = cfg.get("mood")
    if system_prompt is not None:
        pass  # explicit --system-prompt wins
    elif mood is not None:
        if mood not in MOODS:
            console.print(f"[bold red]Error:[/bold red] Unknown mood '{mood}'. Options: {', '.join(MOOD_NAMES)}")
            raise SystemExit(1)
        system_prompt = MOODS[mood]
    else:
        system_prompt = cfg.get("system_prompt")

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

    # Resolve --resume last
    if resume_id == "last":
        storage = Storage()
        resume_id = storage.get_latest_session_id()
        storage.close()
        if resume_id is None:
            console.print("[bold red]Error:[/bold red] No previous sessions to resume.")
            raise SystemExit(1)

    show_stats = show_stats or cfg.get("stats", False)
    sound = sound or cfg.get("sound", False)
    quiet = quiet or cfg.get("quiet", False)
    asyncio.run(_main_loop(base_url, model, api_key, temperature, system_prompt, resume_id, show_stats, sound, quiet))


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
