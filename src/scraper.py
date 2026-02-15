"""Playwright-based X.com feed scraper with persistent browser session."""

import logging
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import BrowserContext, ElementHandle, Page, Playwright, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from .utils import validate_url, parse_timestamp

logger = logging.getLogger(__name__)


class XFeedScraper:
    """Scraper for X.com feed using Playwright browser automation."""

    # Configuration constants
    DEFAULT_VIEWPORT_WIDTH = 1280
    DEFAULT_VIEWPORT_HEIGHT = 900
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    DEFAULT_LOCALE = "de-DE"
    DEFAULT_TIMEZONE = "Europe/Berlin"

    # Scraping constants
    SCROLL_DISTANCE = 800
    MAX_CONSECUTIVE_KNOWN = 3
    SCROLL_MULTIPLIER = 2
    MIN_SCROLL_DELAY = 1.5
    MAX_SCROLL_DELAY = 3.0
    PAGE_LOAD_TIMEOUT = 60000

    # Selectors
    TWEET_SELECTOR = "article[data-testid='tweet']"
    TWEET_TEXT_SELECTOR = "[data-testid='tweetText']"
    SOCIAL_CONTEXT_SELECTOR = "[data-testid='socialContext']"
    REPLY_INDICATOR_SELECTOR = "div[id^='id__']"  # Reply indicator container

    def __init__(
        self,
        profile_path: str = "data/browser-profile",
        headless: bool = True,
    ):
        """
        Initialize the scraper.

        Args:
            profile_path: Path to store the browser profile for persistent sessions.
            headless: Whether to run the browser in headless mode.
        """
        self.profile_path = Path(profile_path)
        self.headless = headless
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def setup_browser(self) -> None:
        """Start Chromium with persistent context from profile_path."""
        self.profile_path.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Setting up browser with profile: {self.profile_path}")

        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_path),
            headless=self.headless,
            channel="chrome",
            viewport={
                "width": self.DEFAULT_VIEWPORT_WIDTH,
                "height": self.DEFAULT_VIEWPORT_HEIGHT,
            },
            user_agent=self.DEFAULT_USER_AGENT,
            locale=self.DEFAULT_LOCALE,
            timezone_id=self.DEFAULT_TIMEZONE,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )
        self.page = self.context.new_page()
        logger.info("Browser setup complete")

    def check_session(self) -> bool:
        """
        Check if there is a valid logged-in session by launching headlessly.

        Navigates to x.com/home and checks whether the browser is redirected
        to a login page. Closes the browser after the check so the real
        scrape starts with a clean slate.

        Returns:
            True if logged in, False if login is needed.
        """
        original_headless = self.headless
        self.headless = True

        try:
            self.setup_browser()

            if self.page is None:
                logger.warning("Could not create browser page for session check")
                return False

            self.page.goto(
                "https://x.com/home",
                wait_until="domcontentloaded",
                timeout=self.PAGE_LOAD_TIMEOUT,
            )
            # Give the page a moment to settle / redirect
            self.page.wait_for_timeout(3000)

            current_url = self.page.url
            logger.debug(f"Session check URL: {current_url}")

            # Negative signals: redirected to login or onboarding flow
            if "/login" in current_url or "/i/flow/" in current_url:
                logger.info("Session check: not logged in (redirected to login)")
                return False

            # Positive signal: compose-tweet button present on the home feed
            compose_btn = self.page.query_selector(
                "[data-testid='SideNav_NewTweet_Button']"
            )
            if compose_btn:
                logger.info("Session check: logged in (compose button found)")
                return True

            # Fallback: if we're still on x.com/home and not redirected, assume OK
            if "x.com/home" in current_url:
                logger.info("Session check: likely logged in (on home feed)")
                return True

            logger.info(f"Session check: uncertain (URL: {current_url})")
            return False

        except PlaywrightError as e:
            logger.error(f"Browser error during session check: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during session check: {e}")
            return False
        finally:
            self.headless = original_headless
            self.close()

    def login_interactive(self) -> bool:
        """
        Open browser in headed mode for manual login.

        Opens X.com, waits for user to log in, then saves session.
        User should press Enter in console when done.

        Returns:
            True if login was successful, False otherwise.
        """
        original_headless = self.headless
        self.headless = False

        try:
            self.setup_browser()

            if self.page is None:
                logger.error("Could not create browser page")
                return False

            logger.info("Navigating to X.com login page...")
            self.page.goto(
                "https://x.com/login",
                wait_until="domcontentloaded",
                timeout=self.PAGE_LOAD_TIMEOUT,
            )

            print("\n" + "=" * 60)
            print("Please log in to X.com in the browser window.")
            print("After logging in successfully, press Enter here to continue...")
            print("=" * 60 + "\n")

            input()

            current_url = self.page.url
            if "x.com" in current_url:
                logger.info("Login successful, session saved")
                return True
            else:
                logger.warning(f"Login may not have been successful. Current URL: {current_url}")
                return False

        except PlaywrightError as e:
            logger.error(f"Browser error during login: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during login: {e}")
            return False
        finally:
            self.headless = original_headless
            self.close()

    def scrape_feed(
        self,
        max_tweets: int = 100,
        stop_on_known: bool = True,
        known_checker: Callable[[str], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Scrape tweets from the X.com feed.

        Args:
            max_tweets: Maximum number of tweets to collect.
            stop_on_known: Stop when consecutive known tweet IDs are found.
            known_checker: Callback function to check if tweet ID is known.

        Returns:
            List of tweet dictionaries.
        """
        if self.page is None:
            self.setup_browser()

        if self.page is None:
            raise RuntimeError("Could not initialize browser")

        tweets: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        consecutive_known = 0
        max_scrolls = max_tweets * self.SCROLL_MULTIPLIER

        try:
            logger.info("Navigating to X.com home...")
            self.page.goto(
                "https://x.com/home",
                wait_until="domcontentloaded",
                timeout=self.PAGE_LOAD_TIMEOUT,
            )
            self._random_delay(2.0, 4.0)

            self._ensure_for_you_tab()
            self._random_delay(1.5, 2.5)

            scroll_count = 0

            while len(tweets) < max_tweets and scroll_count < max_scrolls:
                try:
                    articles = self.page.query_selector_all(self.TWEET_SELECTOR)
                except PlaywrightError as e:
                    logger.warning(f"Failed to query articles: {e}")
                    articles = []

                for article in articles:
                    if len(tweets) >= max_tweets:
                        break

                    tweet = self._parse_tweet(article)
                    if tweet and tweet["id"] and tweet["id"] not in seen_ids:
                        seen_ids.add(tweet["id"])

                        if stop_on_known and known_checker and known_checker(tweet["id"]):
                            consecutive_known += 1
                            logger.debug(f"Found known tweet {tweet['id']} ({consecutive_known}/{self.MAX_CONSECUTIVE_KNOWN})")
                            if consecutive_known >= self.MAX_CONSECUTIVE_KNOWN:
                                logger.info(f"Found {self.MAX_CONSECUTIVE_KNOWN} consecutive known tweets, stopping")
                                return tweets
                        else:
                            consecutive_known = 0
                            tweets.append(tweet)
                            logger.debug(f"Scraped tweet {tweet['id']} from @{tweet.get('author_handle')}")

                self.page.evaluate(f"window.scrollBy(0, {self.SCROLL_DISTANCE})")
                scroll_count += 1
                self._random_delay(self.MIN_SCROLL_DELAY, self.MAX_SCROLL_DELAY)

                self.page.wait_for_timeout(500)

            logger.info(f"Scraping complete: {len(tweets)} tweets collected")

        except PlaywrightError as e:
            logger.error(f"Playwright error during scraping: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during scraping: {e}")

        return tweets

    def _ensure_for_you_tab(self) -> None:
        """Ensure we are on the 'For You' tab (default algorithmic feed)."""
        if self.page is None:
            return

        try:
            # "For You" is the default tab, but let's verify and click if needed
            for_you_tab = self.page.query_selector(
                "a[href='/home'][role='tab']:has-text('For you')"
            )
            if for_you_tab:
                # Check if already selected
                aria_selected = for_you_tab.get_attribute("aria-selected")
                if aria_selected != "true":
                    for_you_tab.click()
                    logger.debug("Clicked 'For You' tab")
                else:
                    logger.debug("Already on 'For You' tab")
                return

            # Alternative selectors for "For You"
            alternative_selectors = [
                "text=For you",
                "[data-testid='ScrollSnap-List'] a:nth-child(1)",
            ]
            for selector in alternative_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element:
                        element.click()
                        logger.debug(f"Clicked 'For You' tab using selector: {selector}")
                        return
                except PlaywrightError:
                    continue

            logger.debug("Could not find 'For You' tab, assuming default view")

        except PlaywrightError as e:
            logger.warning(f"Error ensuring 'For You' tab: {e}")

    def _parse_tweet(self, article: ElementHandle) -> dict[str, Any] | None:
        """
        Parse a tweet from an article element.

        Args:
            article: Playwright ElementHandle for the article.

        Returns:
            Dictionary with tweet data, or None if parsing fails.
        """
        try:
            tweet_data: dict[str, Any] = {
                "id": None,
                "author_handle": None,
                "author_name": None,
                "content": None,
                "timestamp": None,
                "likes": None,
                "retweets": None,
                "replies": None,
                "media_urls": [],
                "is_retweet": False,
                "original_author": None,
                "is_reply": False,
                "reply_to_handle": None,
            }

            # Extract tweet ID first - skip if not found
            tweet_data["id"] = self._extract_tweet_id(article)
            if not tweet_data["id"]:
                return None

            # Check if retweet
            retweet_indicator = article.query_selector(self.SOCIAL_CONTEXT_SELECTOR)
            if retweet_indicator:
                retweet_text = retweet_indicator.inner_text()
                if "reposted" in retweet_text.lower() or "retweeted" in retweet_text.lower():
                    tweet_data["is_retweet"] = True

            # Extract author info
            self._extract_author_info(article, tweet_data)

            # Extract tweet content
            tweet_text_element = article.query_selector(self.TWEET_TEXT_SELECTOR)
            if tweet_text_element:
                tweet_data["content"] = tweet_text_element.inner_text()

            # Check if this is a reply and extract reply context
            self._extract_reply_context(article, tweet_data)

            # Extract timestamp
            time_element = article.query_selector("time")
            if time_element:
                datetime_attr = time_element.get_attribute("datetime")
                tweet_data["timestamp"] = parse_timestamp(datetime_attr)

            # Extract engagement metrics
            tweet_data["likes"] = self._extract_engagement(article, "like")
            tweet_data["retweets"] = self._extract_engagement(article, "retweet")
            tweet_data["replies"] = self._extract_engagement(article, "reply")

            # Extract media URLs with validation
            tweet_data["media_urls"] = self._extract_media_urls(article)

            return tweet_data

        except Exception as e:
            logger.debug(f"Error parsing tweet: {e}")
            return None

    def _extract_author_info(self, article: ElementHandle, tweet_data: dict[str, Any]) -> None:
        """Extract author handle and name from article."""
        try:
            user_links = article.query_selector_all("a[href^='/'][role='link']")
            excluded_prefixes = (
                "search", "explore", "home", "notifications", "messages", "i/"
            )

            for link in user_links:
                href = link.get_attribute("href")
                if href and href.startswith("/") and "/" not in href[1:]:
                    handle = href[1:]
                    if not handle.startswith(excluded_prefixes):
                        if tweet_data["author_handle"] is None:
                            tweet_data["author_handle"] = handle

                            name_element = link.query_selector("span")
                            if name_element:
                                tweet_data["author_name"] = name_element.inner_text()
                        elif tweet_data["is_retweet"] and tweet_data["original_author"] is None:
                            tweet_data["original_author"] = tweet_data["author_handle"]
                            tweet_data["author_handle"] = handle
                        break
        except Exception as e:
            logger.debug(f"Error extracting author info: {e}")

    def _extract_reply_context(self, article: ElementHandle, tweet_data: dict[str, Any]) -> None:
        """
        Detect if tweet is a reply (does NOT fetch parent content - that happens later).

        Args:
            article: Playwright ElementHandle for the article.
            tweet_data: Tweet data dictionary to update.
        """
        try:
            # Method 1: Look for "Replying to" text directly in the article
            article_text = article.inner_text().lower()

            # Check for reply indicators in various languages
            reply_indicators = ["replying to", "antwort an", "in reply to", "als antwort"]
            is_reply_by_text = any(indicator in article_text for indicator in reply_indicators)

            if is_reply_by_text:
                # Find the handle being replied to
                reply_links = article.query_selector_all("a[href^='/'][role='link']")
                for link in reply_links:
                    try:
                        href = link.get_attribute("href")
                        text = link.inner_text()
                        # Look for @handle links that are not the tweet author
                        if (text.startswith("@") and
                            href and
                            href.startswith("/") and
                            "/" not in href[1:] and
                            text[1:] != tweet_data.get("author_handle")):
                            tweet_data["is_reply"] = True
                            tweet_data["reply_to_handle"] = text[1:]
                            logger.debug(f"Found reply to @{tweet_data['reply_to_handle']} (method 1)")
                            break
                    except PlaywrightError:
                        continue

            # Method 2: Check if there's a conversation thread indicator
            # (when X shows the parent tweet above the reply in the feed)
            if not tweet_data["is_reply"]:
                # Look for multiple user sections in the same article
                user_cells = article.query_selector_all("[data-testid='User-Name']")
                if len(user_cells) > 1:
                    # Multiple users in one article often indicates a reply thread
                    tweet_data["is_reply"] = True
                    logger.debug("Found reply (method 2: multiple users)")

        except Exception as e:
            logger.debug(f"Error extracting reply context: {e}")

    def _extract_tweet_id(self, article: ElementHandle) -> str | None:
        """
        Extract tweet ID from article element.

        Args:
            article: Playwright ElementHandle for the article.

        Returns:
            Tweet ID string or None.
        """
        try:
            links = article.query_selector_all("a[href*='/status/']")
            for link in links:
                href = link.get_attribute("href")
                if href:
                    match = re.search(r"/status/(\d+)", href)
                    if match:
                        return match.group(1)

            # Fallback: check time element's parent link
            tweet_link = article.query_selector("a time")
            if tweet_link:
                parent_link = tweet_link.evaluate("el => el.closest('a')?.href")
                if parent_link:
                    match = re.search(r"/status/(\d+)", parent_link)
                    if match:
                        return match.group(1)

        except Exception as e:
            logger.debug(f"Error extracting tweet ID: {e}")

        return None

    def _extract_engagement(self, article: ElementHandle, metric_type: str) -> int | None:
        """
        Extract engagement metric from tweet.

        Args:
            article: Playwright ElementHandle for the article.
            metric_type: Type of metric ('like', 'retweet', 'reply').

        Returns:
            Integer count or None.
        """
        try:
            button = article.query_selector(f"[data-testid='{metric_type}']")
            if not button:
                return None

            # Try aria-label first
            aria_label = button.get_attribute("aria-label")
            if aria_label:
                numbers = re.findall(r"[\d,]+", aria_label)
                if numbers:
                    return int(numbers[0].replace(",", ""))

            # Fallback: check inner span
            span = button.query_selector("span span")
            if span:
                text = span.inner_text()
                if text:
                    # Handle K/M suffixes
                    text = text.strip().upper()
                    multiplier = 1
                    if text.endswith("K"):
                        multiplier = 1000
                        text = text[:-1]
                    elif text.endswith("M"):
                        multiplier = 1000000
                        text = text[:-1]

                    cleaned = text.replace(",", "").replace(".", "")
                    if cleaned.isdigit():
                        return int(cleaned) * multiplier

        except Exception as e:
            logger.debug(f"Error extracting {metric_type}: {e}")

        return None

    def _extract_media_urls(self, article: ElementHandle) -> list[str]:
        """
        Extract and validate media URLs from tweet.

        Args:
            article: Playwright ElementHandle for the article.

        Returns:
            List of validated media URLs.
        """
        urls = []
        try:
            media_images = article.query_selector_all("[data-testid='tweetPhoto'] img")
            for img in media_images:
                src = img.get_attribute("src")
                if src and validate_url(src):
                    urls.append(src)
        except Exception as e:
            logger.debug(f"Error extracting media URLs: {e}")

        return urls

    def _random_delay(self, min_seconds: float, max_seconds: float) -> None:
        """
        Wait for a random amount of time.

        Args:
            min_seconds: Minimum wait time in seconds.
            max_seconds: Maximum wait time in seconds.
        """
        if self.page:
            delay_ms = int(random.uniform(min_seconds, max_seconds) * 1000)
            self.page.wait_for_timeout(delay_ms)

    def close(self) -> None:
        """Close browser and cleanup resources."""
        for resource, name in [(self.page, "page"), (self.context, "context")]:
            if resource:
                try:
                    resource.close()
                except Exception as e:
                    logger.debug(f"Error closing {name}: {e}")

        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                logger.debug(f"Error stopping playwright: {e}")

        self.page = self.context = self.playwright = None
        logger.debug("Browser closed")

    def __enter__(self):
        """Context manager entry."""
        self.setup_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
