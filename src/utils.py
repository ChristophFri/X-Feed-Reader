"""Shared utility functions for X Feed Reader."""

import logging
from datetime import datetime, UTC
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def calculate_engagement_stats(tweets: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate engagement statistics for a list of tweets.

    Args:
        tweets: List of tweet dictionaries.

    Returns:
        Dictionary with engagement statistics.
    """
    if not tweets:
        return {
            "total": 0,
            "authors": 0,
            "retweets": 0,
            "with_media": 0,
            "total_likes": 0,
            "total_retweets": 0,
            "avg_likes": 0.0,
            "avg_retweets": 0.0,
        }

    authors = set(t.get("author_handle") for t in tweets)
    retweet_count = sum(1 for t in tweets if t.get("is_retweet"))
    with_media = sum(1 for t in tweets if t.get("media_urls"))
    total_likes = sum(t.get("likes") or 0 for t in tweets)
    total_retweet_count = sum(t.get("retweets") or 0 for t in tweets)

    return {
        "total": len(tweets),
        "authors": len(authors),
        "retweets": retweet_count,
        "with_media": with_media,
        "total_likes": total_likes,
        "total_retweets": total_retweet_count,
        "avg_likes": round(total_likes / len(tweets), 1),
        "avg_retweets": round(total_retweet_count / len(tweets), 1),
    }


def validate_url(url: str) -> bool:
    """
    Validate that a URL is well-formed and uses http/https.

    Args:
        url: URL string to validate.

    Returns:
        True if valid, False otherwise.
    """
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


def parse_timestamp(timestamp_str: str | None) -> datetime | None:
    """
    Parse an ISO timestamp string to datetime.

    Args:
        timestamp_str: ISO format timestamp string.

    Returns:
        Parsed datetime or None if parsing fails.
    """
    if not timestamp_str:
        return None

    try:
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except ValueError as e:
        logger.debug(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return None


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the application.

    Args:
        verbose: If True, set DEBUG level; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
