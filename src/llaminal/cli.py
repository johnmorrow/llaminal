"""Entry point — shell wrapper launch, click CLI, config resolution."""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

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


async def _run_shell(
    base_url: str | None,
    model: str,
    api_key: str | None,
    temperature: float | None,
    system_prompt: str | None,
    resume_id: str | None,
    show_stats: bool = False,
    shell: str | None = None,
    context_lines: int = 50,
) -> None:
    import os

    from llaminal.ai_mode import AIMode
    from llaminal.cwd_tracker import CwdTracker
    from llaminal.scrollback import ScrollbackCapture
    from llaminal.shell import ShellWrapper

    # Build AI components
    client = None
    if base_url:
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
            if client:
                await client.close()
            storage.close()
            return
        session = Session(system_prompt=system_prompt)
        session.messages = messages
        session_id = resume_id
    else:
        session = Session(system_prompt=system_prompt)
        session_id = storage.create_session(model)
        storage.save_messages(session_id, session.messages, 0)

    # Create shell wrapper
    wrapper = ShellWrapper(shell=shell)

    # Set up scrollback capture with HistoryScreen
    size = os.get_terminal_size()
    scrollback = ScrollbackCapture(size.columns, size.lines)
    wrapper.add_master_output_callback(scrollback.feed)
    wrapper.add_resize_callback(scrollback.resize)

    # Spawn shell first so we have child_pid for CwdTracker
    wrapper.spawn()

    # Track child shell's cwd
    cwd_tracker = CwdTracker(wrapper.child_pid)

    # Create PTY executor and register PTY bash tool (overrides subprocess-based one)
    from llaminal.pty_executor import PtyExecutor
    from llaminal.tools.registry import Tool

    pty_executor = PtyExecutor(wrapper, scrollback)

    async def _pty_bash(command: str) -> str:
        ai_handler._pty_executing = True
        try:
            return await pty_executor.execute(command)
        finally:
            ai_handler._pty_executing = False

    pty_bash_tool = Tool(
        name="bash",
        description="Run a shell command in the user's real shell and return its output. "
        "Commands run with the user's PATH, aliases, virtualenvs, and SSH agent.",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
            },
            "required": ["command"],
        },
        execute=_pty_bash,
    )
    registry.register(pty_bash_tool)

    # Create AI mode handler
    ai_handler = AIMode(
        shell_wrapper=wrapper,
        client=client,
        session=session,
        registry=registry,
        storage=storage,
        session_id=session_id,
        show_stats=show_stats,
        context_provider=lambda: scrollback.get_context(max_lines=context_lines),
        cwd_provider=cwd_tracker.get_cwd,
    )

    # Wire up callbacks — shell only fires toggle(True) on double-ESC entry;
    # AIMode.exit() handles its own return to shell mode.
    wrapper.set_ai_mode_toggle_callback(lambda entering: ai_handler.enter() if entering else None)
    wrapper.set_ai_input_callback(ai_handler.handle_input)
    wrapper.set_fix_it_callback(ai_handler.enter_fix_it)
    wrapper.set_explain_it_callback(ai_handler.enter_explain_it)
    try:
        await wrapper.run()
    finally:
        wrapper.cleanup()
        if client:
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
@click.option("--theme", default=None, type=click.Choice(THEME_NAMES, case_sensitive=False), help="Color theme (default, light, solarized, dracula, catppuccin, llama).")
@click.option("--shell", "shell_cmd", default=None, help="Shell to launch (default: $SHELL).")
@click.option("--context-lines", default=None, type=int, help="Number of terminal lines to capture as AI context (default: 50).")
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
    theme: str | None,
    shell_cmd: str | None,
    context_lines: int | None,
) -> None:
    """Llaminal — your shell, with AI. Double-tap Escape to toggle AI mode."""
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

    # Resolve settings
    model = resolve(model, cfg.get("model"), DEFAULTS["model"])
    api_key = resolve(api_key, cfg.get("api_key"), DEFAULTS["api_key"])
    temperature = resolve(temperature, cfg.get("temperature"), DEFAULTS["temperature"])
    shell_cmd = resolve(shell_cmd, cfg.get("shell"), DEFAULTS["shell"])
    context_lines = resolve(context_lines, cfg.get("context_lines"), DEFAULTS["context_lines"])

    # Mood resolution
    if mood is None:
        mood = cfg.get("mood")
    if system_prompt is not None:
        pass
    elif mood is not None:
        if mood not in MOODS:
            console.print(f"[bold red]Error:[/bold red] Unknown mood '{mood}'. Options: {', '.join(MOOD_NAMES)}")
            raise SystemExit(1)
        system_prompt = MOODS[mood]
    else:
        system_prompt = cfg.get("system_prompt")

    # Base URL resolution
    if base_url is None:
        if port is not None:
            base_url = f"http://localhost:{port}"
        else:
            base_url = resolve(None, cfg.get("base_url"), None)
            if base_url is None and cfg.get("port") is not None:
                base_url = f"http://localhost:{cfg['port']}"

    if base_url is None:
        # Try auto-detection (non-blocking)
        base_url = _auto_detect()

    # No server is NOT fatal anymore — shell still works, AI mode shows a message
    show_stats = show_stats or cfg.get("stats", False)

    # Resolve --resume last
    if resume_id == "last":
        storage = Storage()
        resume_id = storage.get_latest_session_id()
        storage.close()
        if resume_id is None:
            console.print("[bold red]Error:[/bold red] No previous sessions to resume.")
            raise SystemExit(1)

    # Require a real terminal
    if not sys.stdin.isatty():
        console.print("[bold red]Error:[/bold red] llaminal requires an interactive terminal.")
        raise SystemExit(1)

    asyncio.run(
        _run_shell(
            base_url, model, api_key, temperature, system_prompt,
            resume_id, show_stats, shell_cmd, context_lines,
        )
    )


def _auto_detect() -> str | None:
    """Scan common ports for a running LLM server. Returns base_url or None."""
    found = asyncio.run(discover_servers())

    if not found:
        return None

    if len(found) == 1:
        url, _label = found[0]
        return url

    # Multiple servers — just pick the first one (no interactive prompt in raw mode)
    url, _label = found[0]
    return url


if __name__ == "__main__":
    main()
