"""Rotating startup banners — llama art variants and one-liners."""

import random

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from llaminal.themes import get_theme


def _build_llama(base_url: str, eyes: str, tagline: str) -> Text:
    """Build a llama banner with the given eyes and tagline, using active theme."""
    theme = get_theme()
    t = Text()
    t.append("  @@@@@", style=theme.llama_body)
    t.append("     Llaminal", style=f"bold {theme.accent}")
    t.append(" v0.1.0\n", style="dim")
    t.append(" @(", style=theme.llama_body)
    t.append(eyes, style=theme.llama_eyes)
    t.append(")@", style=theme.llama_body)
    t.append(f"    {base_url}\n", style="dim")
    t.append("  (   )~", style=theme.llama_body)
    t.append("\n")
    t.append("   ||||", style=theme.llama_body)
    t.append(f"      {tagline}\n", style="dim italic")
    return t


# One-liner taglines for the random variant
ONE_LINERS = [
    "Type a message to chat. Ctrl+C to cancel, Ctrl+D to exit.",
    "Your local llama is standing by.",
    "No cloud. No API key. Just vibes.",
    "Spitting tokens, not drama.",
    "Locally sourced, organically generated.",
    "Running on your hardware, respecting your privacy.",
    "The terminal is my pasture.",
]

# Banner variants: (eyes, tagline)
_VARIANTS = [
    ("o o", "Type a message to chat. Ctrl+C to cancel, Ctrl+D to exit."),
    ("- -", "Chill mode activated. Let's build something."),
    ("^ o", "Ready when you are. What are we working on?"),
    ("u u", "*yawn* ...ok I'm up. What do you need?"),
]


def print_banner(console: Console, base_url: str) -> None:
    """Print a randomly selected startup banner."""
    theme = get_theme()
    # 50% chance of a fixed variant, 50% chance of a random one-liner
    if random.random() < 0.5:
        eyes, tagline = random.choice(_VARIANTS)
    else:
        eyes = "o o"
        tagline = random.choice(ONE_LINERS)
    banner = _build_llama(base_url, eyes, tagline)
    console.print(Panel(banner, border_style=theme.accent, padding=(0, 1)))
