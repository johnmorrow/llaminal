"""Color theme system — built-in themes for terminal customization."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Semantic color roles for Llaminal's UI."""

    name: str
    accent: str  # primary accent (banner title, banner border)
    llama_body: str  # llama ASCII art body color
    llama_eyes: str  # llama eyes
    tool_border: str  # tool call panel border
    tool_label: str  # "Tool: " label
    tool_name: str  # tool function name
    result_border: str  # tool result panel border
    error: str  # error text
    warning: str  # warning/cancel text


THEMES: dict[str, Theme] = {
    "default": Theme(
        name="default",
        accent="magenta",
        llama_body="rgb(160,100,50)",
        llama_eyes="bold black",
        tool_border="cyan",
        tool_label="bold cyan",
        tool_name="bold white",
        result_border="green",
        error="bold red",
        warning="yellow",
    ),
    "light": Theme(
        name="light",
        accent="blue",
        llama_body="rgb(120,80,40)",
        llama_eyes="bold black",
        tool_border="rgb(0,100,150)",
        tool_label="bold rgb(0,100,150)",
        tool_name="bold black",
        result_border="rgb(0,130,60)",
        error="bold red",
        warning="rgb(180,120,0)",
    ),
    "solarized": Theme(
        name="solarized",
        accent="rgb(38,139,210)",  # solarized blue
        llama_body="rgb(181,137,0)",  # solarized yellow
        llama_eyes="rgb(0,43,54)",  # solarized base03
        tool_border="rgb(42,161,152)",  # solarized cyan
        tool_label="bold rgb(42,161,152)",
        tool_name="bold rgb(253,246,227)",  # solarized base3
        result_border="rgb(133,153,0)",  # solarized green
        error="bold rgb(220,50,47)",  # solarized red
        warning="rgb(203,75,22)",  # solarized orange
    ),
    "dracula": Theme(
        name="dracula",
        accent="rgb(189,147,249)",  # dracula purple
        llama_body="rgb(255,184,108)",  # dracula orange
        llama_eyes="rgb(248,248,242)",  # dracula foreground
        tool_border="rgb(139,233,253)",  # dracula cyan
        tool_label="bold rgb(139,233,253)",
        tool_name="bold rgb(248,248,242)",
        result_border="rgb(80,250,123)",  # dracula green
        error="bold rgb(255,85,85)",  # dracula red
        warning="rgb(241,250,140)",  # dracula yellow
    ),
    "catppuccin": Theme(
        name="catppuccin",
        accent="rgb(203,166,247)",  # catppuccin mauve
        llama_body="rgb(250,179,135)",  # catppuccin peach
        llama_eyes="rgb(205,214,244)",  # catppuccin text
        tool_border="rgb(137,220,235)",  # catppuccin sky
        tool_label="bold rgb(137,220,235)",
        tool_name="bold rgb(205,214,244)",
        result_border="rgb(166,227,161)",  # catppuccin green
        error="bold rgb(243,139,168)",  # catppuccin red
        warning="rgb(249,226,175)",  # catppuccin yellow
    ),
    "llama": Theme(
        name="llama",
        accent="rgb(210,140,60)",  # warm amber
        llama_body="rgb(180,120,50)",  # desert sand
        llama_eyes="rgb(60,40,20)",  # dark brown
        tool_border="rgb(190,160,100)",  # sandy
        tool_label="bold rgb(190,160,100)",
        tool_name="bold rgb(240,220,180)",  # cream
        result_border="rgb(140,170,80)",  # desert sage
        error="bold rgb(200,60,40)",  # terracotta
        warning="rgb(220,180,60)",  # golden
    ),
}

THEME_NAMES = sorted(THEMES.keys())

# Module-level active theme — set at startup
_active_theme: Theme = THEMES["default"]


def set_theme(name: str) -> None:
    """Set the active theme by name."""
    global _active_theme
    _active_theme = THEMES[name]


def get_theme() -> Theme:
    """Get the currently active theme."""
    return _active_theme
