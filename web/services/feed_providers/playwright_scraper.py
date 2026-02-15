"""Playwright feed provider — wraps existing src/scraper.py via asyncio.to_thread()."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.scraper import XFeedScraper

logger = logging.getLogger(__name__)


class SessionExpiredError(Exception):
    """Raised when the browser session is no longer valid."""


class PlaywrightFeedProvider:
    """Fetches tweets by running the existing Playwright scraper in a thread."""

    # The CLI's browser profile path — reused for the admin/first user
    CLI_PROFILE = "data/browser-profile"

    def __init__(self, base_profile_dir: str = "data/browser-profiles"):
        self.base_profile_dir = Path(base_profile_dir)

    def _get_profile_path(self, user_id: int) -> str:
        """Per-user browser profile directory.

        Reuses the existing CLI profile if it exists (local dev with single user).
        In production, each user would need their own authenticated profile.
        """
        cli_path = Path(self.CLI_PROFILE)
        if cli_path.exists():
            return str(cli_path)
        path = self.base_profile_dir / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    async def fetch_feed(self, user_id: int, max_tweets: int = 100) -> list[dict[str, Any]]:
        """Run the Playwright scraper in a thread pool.

        Checks session validity after navigating to x.com/home — if redirected
        to a login page, raises SessionExpiredError immediately instead of
        scrolling for 10 minutes on a login page.
        """
        profile_path = self._get_profile_path(user_id)
        logger.info(f"Playwright scraper using profile: {profile_path}")

        def _scrape():
            scraper = XFeedScraper(profile_path=profile_path, headless=True)
            try:
                scraper.setup_browser()

                # Navigate and check if session is valid before scraping
                scraper.page.goto(
                    "https://x.com/home",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                scraper.page.wait_for_timeout(5000)
                current_url = scraper.page.url
                logger.info(f"Playwright navigated to: {current_url}")

                if "/login" in current_url or "/i/flow/" in current_url:
                    raise SessionExpiredError(
                        "X.com browser session expired. Run 'python login_helper.py' to re-login."
                    )

                # Session is valid — now scrape (page is already on /home)
                tweets = scraper.scrape_feed(max_tweets=max_tweets, stop_on_known=False)
                return tweets
            finally:
                scraper.close()

        tweets = await asyncio.to_thread(_scrape)
        logger.info(f"Playwright scraped {len(tweets)} tweets for user {user_id}")
        return tweets

    async def check_connection(self, user_id: int) -> bool:
        """Check if the Playwright session is valid for this user."""
        profile_path = self._get_profile_path(user_id)

        def _check():
            scraper = XFeedScraper(profile_path=profile_path, headless=True)
            # check_session() handles its own setup_browser() and close()
            return scraper.check_session()

        try:
            return await asyncio.to_thread(_check)
        except Exception as e:
            logger.error(f"Playwright session check failed for user {user_id}: {e}")
            return False
