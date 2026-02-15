"""CLI for X Feed Reader using Typer."""

import logging
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Annotated, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .config import (
    Config,
    get_default_config_path,
    load_config,
    save_template_config,
    show_config,
)
from .database import Database, init_db
from .scraper import XFeedScraper
from .summarizer import generate_summary_lmstudio
from .utils import calculate_engagement_stats
from .telegram_notifier import send_summary_to_telegram
from .utils import setup_logging

# Load .env from project directory only
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path, override=False)

# Load configuration
_config = load_config()

# CLI styles
STYLE_HEADER = "bold blue"
STYLE_SUCCESS = "bold green"
STYLE_WARNING = "bold yellow"
STYLE_ERROR = "bold red"

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="xfeed",
    help="X Feed Reader - Scrape and summarize your X.com feed locally.",
    add_completion=False,
    invoke_without_command=True,
)
console = Console()


def _get_db(db_path: str) -> Database:
    """Get initialized database instance."""
    return init_db(db_path)


def _configure_logging(verbose: bool) -> None:
    """Configure logging based on verbose flag."""
    setup_logging(verbose)


# ---------------------------------------------------------------------------
# Auto-pilot: default pipeline when `xfeed` is invoked without a subcommand
# ---------------------------------------------------------------------------

def _ensure_config_exists() -> None:
    """Create config.yaml from template if it does not exist yet."""
    config_path = get_default_config_path()
    if not config_path.exists():
        saved = save_template_config(config_path)
        console.print(f"[{STYLE_SUCCESS}]Created default config: {saved}[/{STYLE_SUCCESS}]")


def _maybe_send_telegram(summary_text: str, stats: dict) -> None:
    """Send summary to Telegram if credentials are configured."""
    bot_token = _config.telegram.bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = _config.telegram.chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if bot_token and chat_id:
        console.print("Sending summary to Telegram...")
        success = send_summary_to_telegram(bot_token, chat_id, summary_text, stats)
        if success:
            console.print(f"[{STYLE_SUCCESS}]Summary sent to Telegram![/{STYLE_SUCCESS}]")
        else:
            console.print(f"[{STYLE_ERROR}]Failed to send to Telegram.[/{STYLE_ERROR}]")


def _run_full_pipeline(*, verbose: bool = False) -> None:
    """
    Execute the full scrape-summarize-notify pipeline with a progress bar.

    Steps:
        1. Check session  (0-20 %)
        2. Scrape          (20-60 %)
        3. Summarize       (60-90 %)
        4. Send Telegram   (90-100 %)
    """
    _configure_logging(verbose)

    profile_path = _config.browser_profile
    db_path = _config.db_path
    max_tweets = _config.scrape.max_tweets
    headed = _config.scrape.headed
    hours = _config.summary.hours

    with Progress(
        SpinnerColumn("simpleDots"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Starting...", total=100)

        # ── 1. Check session (0-20%) ──────────────────────────────────
        progress.update(task, description="Checking session...", completed=0)
        scraper = XFeedScraper(profile_path=profile_path, headless=True)
        logged_in = scraper.check_session()

        if not logged_in:
            progress.stop()
            console.print(
                f"[{STYLE_WARNING}]No active session found. "
                f"Opening browser for login...[/{STYLE_WARNING}]"
            )
            login_scraper = XFeedScraper(profile_path=profile_path, headless=False)
            success = login_scraper.login_interactive()
            if not success:
                console.print(f"[{STYLE_ERROR}]Login failed. Aborting.[/{STYLE_ERROR}]")
                raise typer.Exit(1)
            console.print(f"[{STYLE_SUCCESS}]Login successful! Resuming pipeline...[/{STYLE_SUCCESS}]")
            progress.start()

        progress.update(task, description="Session OK", completed=20)

        # ── 2. Scrape (20-60%) ────────────────────────────────────────
        progress.update(task, description="Scraping feed...", completed=20)
        db = _get_db(db_path)
        started_at = datetime.now(UTC)

        feed_scraper = XFeedScraper(profile_path=profile_path, headless=not headed)
        try:
            feed_scraper.setup_browser()
            tweets = feed_scraper.scrape_feed(
                max_tweets=max_tweets,
                stop_on_known=True,
                known_checker=db.tweet_exists,
            )
            new_count = db.add_tweets(tweets)
            db.cleanup_old_tweets(keep_count=100)
            finished_at = datetime.now(UTC)
            db.log_scrape_run(
                started_at=started_at,
                finished_at=finished_at,
                tweets_found=len(tweets),
                tweets_new=new_count,
                status="completed",
            )
        except Exception as e:
            finished_at = datetime.now(UTC)
            db.log_scrape_run(
                started_at=started_at,
                finished_at=finished_at,
                tweets_found=0,
                tweets_new=0,
                status=f"failed: {str(e)[:100]}",
            )
            progress.stop()
            console.print(f"[{STYLE_ERROR}]Scrape failed: {e}[/{STYLE_ERROR}]")
            raise typer.Exit(1)
        finally:
            feed_scraper.close()

        progress.update(task, description=f"Scraped {len(tweets)} tweets ({new_count} new)", completed=60)

        # ── 3. Summarize (60-90%) ────────────────────────────────────
        progress.update(task, description="Summarizing...", completed=60)
        db_tweets = db.get_tweets_since(since_hours=hours)
        if not db_tweets:
            progress.stop()
            console.print(f"[{STYLE_WARNING}]No tweets found for summary.[/{STYLE_WARNING}]")
            raise typer.Exit(0)

        tweet_dicts = [t.to_dict() for t in db_tweets]

        url = _config.summary.lmstudio_url or os.getenv("LMSTUDIO_URL", "http://localhost:1234")
        summary_text = generate_summary_lmstudio(tweet_dicts, base_url=url, max_tweets=max_tweets)

        stats = calculate_engagement_stats(tweet_dicts)
        db_stats = db.get_stats()
        stats.update(db_stats)
        stats["hours"] = hours

        progress.update(task, description="Summary ready", completed=90)

        # ── 4. Send Telegram (90-100%) ────────────────────────────────
        progress.update(task, description="Sending notifications...", completed=90)

    # Post-pipeline: Telegram (outside progress bar)
    _maybe_send_telegram(summary_text, stats)

    console.print(f"\n[{STYLE_SUCCESS}]Pipeline complete![/{STYLE_SUCCESS}]")


def _start_scheduler(every: str, verbose: bool) -> None:
    """Parse interval, run pipeline once, then hand off to the scheduler."""
    from .scheduler import parse_interval, run_scheduler

    try:
        interval = parse_interval(every)
    except ValueError as e:
        console.print(f"[{STYLE_ERROR}]{e}[/{STYLE_ERROR}]")
        raise typer.Exit(1)

    console.print(f"[{STYLE_HEADER}]Running initial pipeline...[/{STYLE_HEADER}]")
    _run_full_pipeline(verbose=verbose)

    console.print(f"\n[{STYLE_HEADER}]Starting scheduler (every {every})...[/{STYLE_HEADER}]")
    run_scheduler(
        interval=interval,
        pipeline_func=lambda: _run_full_pipeline(verbose=verbose),
        interval_str=every,
        use_tray=True,
    )


@app.callback(invoke_without_command=True)
def _default_command(
    ctx: typer.Context,
    every: Annotated[Optional[str], typer.Option(help="Schedule interval, e.g. 30m, 6h, 1d")] = None,
    verbose: Annotated[Optional[bool], typer.Option(help="Verbose output")] = None,
) -> None:
    """
    Auto-pilot mode (default).

    When invoked without a subcommand, runs the full pipeline:
    check session -> scrape -> summarize -> send Telegram.

    Use --every to start a background scheduler with a system tray icon.
    """
    # If a subcommand was given, let Typer handle it
    if ctx.invoked_subcommand is not None:
        return

    verbose = verbose if verbose is not None else _config.verbose

    _ensure_config_exists()

    if every:
        _start_scheduler(every, verbose)
    else:
        _run_full_pipeline(verbose=verbose)


@app.command()
def login(
    profile_path: Annotated[
        Optional[str], typer.Option(help="Path to browser profile")
    ] = None,
    verbose: Annotated[Optional[bool], typer.Option(help="Verbose output")] = None,
):
    """
    Open browser for manual X.com login.

    Opens a browser window where you can log in to X.com manually.
    The session will be saved for future scraping runs.
    """
    # Apply config defaults
    profile_path = profile_path or _config.browser_profile
    verbose = verbose if verbose is not None else _config.verbose

    _configure_logging(verbose)

    console.print(f"[{STYLE_HEADER}]Starting login process...[/{STYLE_HEADER}]")

    scraper = XFeedScraper(profile_path=profile_path, headless=False)

    try:
        success = scraper.login_interactive()
        if success:
            console.print(f"[{STYLE_SUCCESS}]Login successful![/{STYLE_SUCCESS}]")
            console.print(f"Session saved to: {profile_path}")
        else:
            console.print(f"[{STYLE_WARNING}]Login may not have been successful.[/{STYLE_WARNING}]")
            console.print("Please try again.")
    except Exception as e:
        console.print(f"[{STYLE_ERROR}]Error during login: {e}[/{STYLE_ERROR}]")
        raise typer.Exit(1)


# Config subcommand group
config_app = typer.Typer(help="Configuration management commands.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show():
    """
    Show current configuration.

    Displays all current settings including values from config file,
    environment variables, and defaults.
    """
    config_path = get_default_config_path()
    console.print(f"[{STYLE_HEADER}]Config file: {config_path}[/{STYLE_HEADER}]")
    if config_path.exists():
        console.print(f"[{STYLE_SUCCESS}]  (exists)[/{STYLE_SUCCESS}]")
    else:
        console.print(f"[{STYLE_WARNING}]  (not found - using defaults)[/{STYLE_WARNING}]")
    console.print()
    console.print(show_config(_config))


@config_app.command("init")
def config_init(
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing config")] = False,
):
    """
    Initialize configuration file.

    Creates a template config.yaml in the current directory with
    commented defaults that you can customize.
    """
    config_path = get_default_config_path()

    if config_path.exists() and not force:
        console.print(f"[{STYLE_WARNING}]Config file already exists: {config_path}[/{STYLE_WARNING}]")
        console.print("Use --force to overwrite.")
        raise typer.Exit(1)

    saved_path = save_template_config(config_path)
    console.print(f"[{STYLE_SUCCESS}]Config file created: {saved_path}[/{STYLE_SUCCESS}]")
    console.print("\nEdit this file to customize your settings.")


@config_app.command("path")
def config_path():
    """
    Show the config file path.

    Prints the path where the config file should be located.
    """
    config_path = get_default_config_path()
    console.print(str(config_path))


if __name__ == "__main__":
    app()
