"""Twitter API v2 feed provider — fetches the user's home timeline."""

import logging
from datetime import datetime, timedelta, UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.constants import (
    DEFAULT_TOKEN_EXPIRY,
    EXPANSIONS,
    TOKEN_REFRESH_THRESHOLD_MINUTES,
    TWEET_FIELDS,
    TWITTER_API_MAX_RESULTS,
    TWITTER_API_TIMEOUT,
    TWITTER_CONNECTION_CHECK_TIMEOUT,
    TWITTER_TIMELINE_URL,
    TWITTER_USER_ME_URL,
    USER_FIELDS,
)
from web.db.encryption import decrypt
from web.http_client import get_http_client
from web.models.user import User
from web.services.twitter_oauth import refresh_access_token

logger = logging.getLogger(__name__)


class TwitterAPIProvider:
    """Fetches tweets via Twitter API v2."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_access_token(self, user_id: int) -> tuple[str, str]:
        """Get a valid access token for the user, refreshing if needed.

        Returns (access_token, x_user_id).
        """
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.x_access_token:
            raise ValueError(f"User {user_id} has no X access token")

        access_token = decrypt(user.x_access_token)

        # Check if token needs refresh (expires within threshold)
        expires_at = user.x_token_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at and expires_at < datetime.now(UTC) + timedelta(minutes=TOKEN_REFRESH_THRESHOLD_MINUTES):
            if not user.x_refresh_token:
                raise ValueError(f"User {user_id} token expired and no refresh token available")
            refresh = decrypt(user.x_refresh_token)
            token_data = await refresh_access_token(refresh)
            from web.db.encryption import encrypt
            user.x_access_token = encrypt(token_data["access_token"])
            if token_data.get("refresh_token"):
                user.x_refresh_token = encrypt(token_data["refresh_token"])
            user.x_token_expires_at = datetime.now(UTC) + timedelta(seconds=token_data.get("expires_in", DEFAULT_TOKEN_EXPIRY))
            await self.db.commit()
            access_token = token_data["access_token"]

        return access_token, user.x_user_id

    async def fetch_feed(self, user_id: int, max_tweets: int = 100) -> list[dict[str, Any]]:
        """Fetch the user's home timeline via Twitter API v2."""
        access_token, x_user_id = await self._get_access_token(user_id)

        url = TWITTER_TIMELINE_URL.format(user_id=x_user_id)
        params = {
            "max_results": min(max_tweets, TWITTER_API_MAX_RESULTS),
            "tweet.fields": TWEET_FIELDS,
            "user.fields": USER_FIELDS,
            "expansions": EXPANSIONS,
        }

        client = get_http_client()
        resp = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TWITTER_API_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        if "data" not in data:
            logger.warning("No tweet data in API response for user %s", user_id)
            return []

        # Build user lookup from includes
        users_map = {}
        for u in data.get("includes", {}).get("users", []):
            users_map[u["id"]] = u

        # Build referenced tweets lookup
        ref_tweets_map = {}
        for rt in data.get("includes", {}).get("tweets", []):
            ref_tweets_map[rt["id"]] = rt

        tweets = []
        for tweet in data["data"]:
            tweets.append(self._transform_tweet(tweet, users_map, ref_tweets_map))

        logger.info("Fetched %d tweets via API for user %s", len(tweets), user_id)
        return tweets

    def _transform_tweet(
        self,
        tweet: dict,
        users_map: dict,
        ref_tweets_map: dict,
    ) -> dict[str, Any]:
        """Transform a Twitter API v2 tweet to the canonical dict shape."""
        author = users_map.get(tweet.get("author_id"), {})
        metrics = tweet.get("public_metrics", {})

        # Check for retweet or reply
        is_retweet = False
        is_reply = False
        original_author = None
        reply_to_handle = None

        for ref in tweet.get("referenced_tweets", []):
            if ref["type"] == "retweeted":
                is_retweet = True
                ref_tweet = ref_tweets_map.get(ref["id"], {})
                ref_author = users_map.get(ref_tweet.get("author_id"), {})
                original_author = ref_author.get("username")
            elif ref["type"] == "replied_to":
                is_reply = True
                ref_tweet = ref_tweets_map.get(ref["id"], {})
                ref_author = users_map.get(ref_tweet.get("author_id"), {})
                reply_to_handle = ref_author.get("username")

        # Extract media URLs from entities
        media_urls = []
        if tweet.get("entities", {}).get("urls"):
            for url_entity in tweet["entities"]["urls"]:
                expanded = url_entity.get("expanded_url", "")
                if any(ext in expanded for ext in [".jpg", ".png", ".gif", "pbs.twimg.com"]):
                    media_urls.append(expanded)

        return {
            "id": tweet["id"],
            "author_handle": author.get("username"),
            "author_name": author.get("name"),
            "content": tweet.get("text"),
            "timestamp": tweet.get("created_at"),
            "likes": metrics.get("like_count"),
            "retweets": metrics.get("retweet_count"),
            "replies": metrics.get("reply_count"),
            "media_urls": media_urls or None,
            "is_retweet": is_retweet,
            "original_author": original_author,
            "is_reply": is_reply,
            "reply_to_handle": reply_to_handle,
        }

    async def check_connection(self, user_id: int) -> bool:
        """Verify the user's Twitter API access is working."""
        try:
            access_token, x_user_id = await self._get_access_token(user_id)
            client = get_http_client()
            resp = await client.get(
                TWITTER_USER_ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=TWITTER_CONNECTION_CHECK_TIMEOUT,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("Twitter API connection check failed for user %s: %s", user_id, e)
            return False
