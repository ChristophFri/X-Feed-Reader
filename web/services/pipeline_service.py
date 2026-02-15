"""Pipeline orchestrator — per-user: fetch → store → summarize → deliver."""

import logging
from datetime import datetime, timedelta, UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils import now_utc, calculate_engagement_stats
from web.models.briefing import Briefing
from web.models.scrape_run import ScrapeRun
from web.models.tweet import Tweet as WebTweet
from web.models.user_settings import UserSettings
from web.services.feed_providers.twitter_api import TwitterAPIProvider
from web.services.summary_service import SummaryGenerationError, generate_summary

logger = logging.getLogger(__name__)


async def run_user_pipeline(user_id: int, db: AsyncSession) -> Briefing | None:
    """Run the full pipeline for a single user: fetch → store → summarize → store briefing.

    Returns the created Briefing, or None on failure.
    """
    # Load settings
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if not settings:
        logger.error("No settings found for user %s", user_id)
        return None

    started_at = now_utc()
    feed_source = settings.feed_source

    try:
        # --- Step 1: Fetch tweets ---
        if feed_source == "api":
            provider = TwitterAPIProvider(db)
            raw_tweets = await provider.fetch_feed(user_id, max_tweets=settings.max_tweets)
        elif feed_source == "scraper":
            from web.config import get_settings as get_app_settings

            app_settings = get_app_settings()
            if app_settings.disable_playwright:
                logger.error("Playwright scraping is disabled in this environment (user %s)", user_id)
                await _log_scrape_run(db, user_id, started_at, 0, 0, feed_source, "error: playwright_disabled")
                return None

            from web.services.feed_providers.playwright_scraper import PlaywrightFeedProvider, SessionExpiredError

            provider = PlaywrightFeedProvider()
            try:
                raw_tweets = await provider.fetch_feed(user_id, max_tweets=settings.max_tweets)
            except SessionExpiredError as e:
                await _log_scrape_run(db, user_id, started_at, 0, 0, feed_source, f"error: {e}")
                raise
        else:
            logger.error("Unknown feed source '%s' for user %s", feed_source, user_id)
            raw_tweets = []

        if not raw_tweets:
            logger.info("No tweets fetched for user %s", user_id)
            await _log_scrape_run(db, user_id, started_at, 0, 0, feed_source, "no_tweets")
            return None

        # --- Step 2: Store tweets (batch dedup) ---
        new_count = await _store_tweets_batch(db, user_id, raw_tweets)

        await _log_scrape_run(
            db, user_id, started_at, len(raw_tweets), new_count, feed_source, "completed"
        )

        # --- Step 3: Get recent tweets for summarization ---
        cutoff = now_utc() - timedelta(hours=settings.summary_hours)
        recent_result = await db.execute(
            select(WebTweet)
            .where(WebTweet.user_id == user_id, WebTweet.scraped_at >= cutoff)
            .order_by(WebTweet.timestamp.desc())
        )
        recent_tweets = recent_result.scalars().all()

        if not recent_tweets:
            logger.info("No recent tweets to summarize for user %s", user_id)
            return None

        # Convert to dicts for summarizer
        tweet_dicts = [
            {
                "id": t.tweet_id,
                "author_handle": t.author_handle,
                "author_name": t.author_name,
                "content": t.content,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "likes": t.likes,
                "retweets": t.retweets,
                "replies": t.replies,
                "media_urls": t.media_urls,
                "is_retweet": t.is_retweet,
                "original_author": t.original_author,
                "is_reply": t.is_reply,
                "reply_to_handle": t.reply_to_handle,
            }
            for t in recent_tweets
        ]

        # --- Step 4: Summarize ---
        try:
            summary = await generate_summary(
                tweets=tweet_dicts,
                provider=settings.llm_provider,
                model=settings.llm_model,
                preset=settings.prompt_preset,
                custom_prompt=settings.custom_prompt,
            )
        except SummaryGenerationError as e:
            logger.error("Summary generation failed for user %s: %s", user_id, e)
            await _log_scrape_run(db, user_id, started_at, len(raw_tweets), new_count, feed_source, f"summary_error: {e}")
            return None

        # --- Step 5: Store briefing ---
        briefing = Briefing(
            user_id=user_id,
            content=summary,
            tweet_count=len(tweet_dicts),
            llm_provider=settings.llm_provider,
            prompt_preset=settings.prompt_preset,
        )
        db.add(briefing)
        await db.commit()
        await db.refresh(briefing)

        logger.info(
            "Pipeline complete for user %s: %d fetched, %d new, %d summarized",
            user_id, len(raw_tweets), new_count, len(tweet_dicts),
        )
        return briefing

    except SummaryGenerationError:
        # Already handled above, but re-raise if it somehow reaches here
        raise
    except Exception as e:
        logger.error("Pipeline failed for user %s: %s", user_id, e, exc_info=True)
        try:
            await db.rollback()
            await _log_scrape_run(db, user_id, started_at, 0, 0, feed_source, f"error: {e}")
        except Exception as log_err:
            logger.error("Failed to log scrape run after pipeline error: %s", log_err)
        return None


async def _store_tweets_batch(
    db: AsyncSession, user_id: int, raw_tweets: list[dict[str, Any]]
) -> int:
    """Store tweets using batch dedup — single query to check existence, then bulk insert.

    Returns count of newly stored tweets.
    """
    from src.utils import parse_timestamp

    # Collect all tweet IDs from raw data
    tweet_ids = [t.get("id") for t in raw_tweets if t.get("id")]
    if not tweet_ids:
        return 0

    # Batch-fetch existing tweet IDs in a single query
    existing_result = await db.execute(
        select(WebTweet.tweet_id).where(
            WebTweet.tweet_id.in_(tweet_ids),
            WebTweet.user_id == user_id,
        )
    )
    existing_ids = {row[0] for row in existing_result.all()}

    # Insert only new tweets
    new_count = 0
    for tweet_data in raw_tweets:
        tweet_id = tweet_data.get("id")
        if not tweet_id or tweet_id in existing_ids:
            continue

        tweet = WebTweet(
            tweet_id=tweet_id,
            user_id=user_id,
            author_handle=tweet_data.get("author_handle"),
            author_name=tweet_data.get("author_name"),
            content=tweet_data.get("content"),
            timestamp=parse_timestamp(tweet_data.get("timestamp")) if isinstance(tweet_data.get("timestamp"), str) else tweet_data.get("timestamp"),
            likes=tweet_data.get("likes"),
            retweets=tweet_data.get("retweets"),
            replies=tweet_data.get("replies"),
            media_urls=tweet_data.get("media_urls"),
            is_retweet=tweet_data.get("is_retweet", False),
            original_author=tweet_data.get("original_author"),
            is_reply=tweet_data.get("is_reply", False),
            reply_to_handle=tweet_data.get("reply_to_handle"),
        )
        db.add(tweet)
        new_count += 1

    if new_count:
        await db.commit()

    return new_count


async def _log_scrape_run(
    db: AsyncSession,
    user_id: int,
    started_at: datetime,
    tweets_found: int,
    tweets_new: int,
    feed_source: str,
    status: str,
) -> None:
    run = ScrapeRun(
        user_id=user_id,
        started_at=started_at,
        finished_at=now_utc(),
        tweets_found=tweets_found,
        tweets_new=tweets_new,
        feed_source=feed_source,
        status=status,
    )
    db.add(run)
    await db.commit()
