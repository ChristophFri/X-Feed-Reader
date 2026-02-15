"""Configuration management for X Feed Reader."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_CONFIG_FILENAME = "config.yaml"


def get_default_config_dir() -> Path:
    """Get the default configuration directory (current working directory)."""
    return Path.cwd()


def get_default_config_path() -> Path:
    """Get the default configuration file path.

    Looks for config.yaml in the current working directory.
    """
    return get_default_config_dir() / DEFAULT_CONFIG_FILENAME


@dataclass
class TelegramConfig:
    """Telegram notification settings."""

    bot_token: str = ""
    chat_id: str = ""


@dataclass
class SummaryConfig:
    """Summary generation settings."""

    hours: int = 24
    lmstudio_url: str = "http://localhost:1234"


@dataclass
class ScrapeConfig:
    """Scraping settings."""

    max_tweets: int = 100
    headed: bool = False


@dataclass
class Config:
    """Main configuration container."""

    browser_profile: str = "data/browser-profile"
    db_path: str = "data/x_feed.db"
    verbose: bool = False

    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    summary: SummaryConfig = field(default_factory=SummaryConfig)
    scrape: ScrapeConfig = field(default_factory=ScrapeConfig)


def _resolve_path(path_str: str) -> str:
    """Resolve a path string, expanding ~ and making absolute."""
    if not path_str:
        return path_str
    path = Path(path_str).expanduser()
    return str(path)


def _load_yaml_config(config_path: Path) -> dict:
    """Load configuration from a YAML file."""
    if not config_path.exists():
        return {}

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data if data else {}


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Load configuration from YAML file.

    Priority: defaults < config file < environment variables

    Args:
        config_path: Path to config file. If None, uses default location.

    Returns:
        Config object with loaded settings.
    """
    if config_path is None:
        config_path = get_default_config_path()

    config = Config()
    data = _load_yaml_config(config_path)

    if not data:
        return config

    # Top-level settings
    if "browser_profile" in data:
        config.browser_profile = _resolve_path(data["browser_profile"])
    if "db_path" in data:
        config.db_path = _resolve_path(data["db_path"])
    if "verbose" in data:
        config.verbose = bool(data["verbose"])

    # Telegram settings
    if "telegram" in data and isinstance(data["telegram"], dict):
        tg = data["telegram"]
        config.telegram.bot_token = tg.get("bot_token", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
        config.telegram.chat_id = tg.get("chat_id", "") or os.getenv("TELEGRAM_CHAT_ID", "")

    # Summary settings
    if "summary" in data and isinstance(data["summary"], dict):
        s = data["summary"]
        if "hours" in s:
            config.summary.hours = int(s["hours"])
        if "lmstudio_url" in s:
            config.summary.lmstudio_url = s["lmstudio_url"]

    # Scrape settings
    if "scrape" in data and isinstance(data["scrape"], dict):
        sc = data["scrape"]
        if "max_tweets" in sc:
            config.scrape.max_tweets = int(sc["max_tweets"])
        if "headed" in sc:
            config.scrape.headed = bool(sc["headed"])

    return config


def get_template_config() -> str:
    """Get a template configuration file content."""
    return '''# X Feed Reader Configuration
# Place this file in the project root directory

# Browser profile directory for persistent login
browser_profile: "data/browser-profile"

# SQLite database path
db_path: "data/x_feed.db"

# Enable verbose logging
verbose: false

# Telegram notification settings
telegram:
  bot_token: ""  # Or set TELEGRAM_BOT_TOKEN env var
  chat_id: ""    # Or set TELEGRAM_CHAT_ID env var

# Summary generation settings
summary:
  hours: 24           # Hours to look back for tweets
  lmstudio_url: "http://localhost:1234"  # LM Studio server URL

# Scraping settings
scrape:
  max_tweets: 100     # Maximum tweets to scrape
  headed: false       # Run browser in headed (visible) mode
'''


def save_template_config(config_path: Optional[Path] = None) -> Path:
    """
    Save template configuration to file.

    Args:
        config_path: Path to save config. If None, uses default location.

    Returns:
        Path where config was saved.
    """
    if config_path is None:
        config_path = get_default_config_path()

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(get_template_config())

    return config_path


def show_config(config: Config) -> str:
    """Format config for display."""
    lines = [
        "Current Configuration:",
        "",
        f"  browser_profile: {config.browser_profile}",
        f"  db_path: {config.db_path}",
        f"  verbose: {config.verbose}",
        "",
        "  telegram:",
        f"    bot_token: {'***' if config.telegram.bot_token else '(not set)'}",
        f"    chat_id: {config.telegram.chat_id or '(not set)'}",
        "",
        "  summary:",
        f"    hours: {config.summary.hours}",
        f"    lmstudio_url: {config.summary.lmstudio_url}",
        "",
        "  scrape:",
        f"    max_tweets: {config.scrape.max_tweets}",
        f"    headed: {config.scrape.headed}",
    ]
    return "\n".join(lines)
