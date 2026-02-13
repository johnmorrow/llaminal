"""Config file loading and resolution."""

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "llaminal" / "config.toml"

DEFAULTS: dict[str, Any] = {
    "base_url": None,
    "port": 8080,
    "model": "local-model",
    "api_key": None,
    "temperature": None,
    "system_prompt": None,
}


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config from TOML file. Returns empty dict if file doesn't exist."""
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return {}
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def resolve(cli_value: Any, config_value: Any, default: Any) -> Any:
    """Resolve a setting with precedence: CLI flag > config file > default."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default
