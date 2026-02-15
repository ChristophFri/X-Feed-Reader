"""FeedProvider protocol — common interface for tweet fetching."""

from typing import Any, Protocol


class FeedProvider(Protocol):
    """Protocol for feed data providers (Twitter API, Playwright scraper, etc.)."""

    async def fetch_feed(self, user_id: int, max_tweets: int = 100) -> list[dict[str, Any]]:
        """Fetch tweets from the user's feed.

        Returns list of dicts matching the canonical tweet shape from src/scraper.py _parse_tweet().
        """
        ...

    async def check_connection(self, user_id: int) -> bool:
        """Verify the feed source is connected and accessible for this user."""
        ...
