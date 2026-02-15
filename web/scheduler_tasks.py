"""Scheduler tasks — determines which users need pipeline runs."""

import logging
from datetime import datetime, timedelta, UTC

from arq import ArqRedis
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from web.constants import DUPLICATE_BRIEFING_HOURS
from web.db.session import async_session_factory
from web.models.briefing import Briefing
from web.models.subscription import Subscription
from web.models.user import User
from web.models.user_settings import UserSettings

logger = logging.getLogger(__name__)


def _utc_hour_for_user(schedule_hour: int, timezone: str) -> int:
    """Convert a user's local schedule_hour to the current UTC hour equivalent.

    Simple offset-based approach using zoneinfo.
    """
    try:
        from zoneinfo import ZoneInfo

        now_local = datetime.now(ZoneInfo(timezone))
        utc_offset_hours = now_local.utcoffset().total_seconds() / 3600
        utc_hour = (schedule_hour - utc_offset_hours) % 24
        return int(utc_hour)
    except Exception as e:
        logger.warning(
            "Invalid timezone '%s' for schedule_hour %d, falling back to UTC: %s",
            timezone, schedule_hour, e,
        )
        return schedule_hour  # Fallback: treat as UTC


async def enqueue_due_users(ctx: dict) -> None:
    """Find users whose scheduled hour matches now and enqueue their pipeline runs.

    Runs every hour via ARQ cron.
    """
    current_utc_hour = datetime.now(UTC).hour
    redis: ArqRedis = ctx.get("redis") or ctx.get("arq_redis")

    async with async_session_factory() as db:
        # Get all active users with settings and active subscriptions
        result = await db.execute(
            select(User, UserSettings, Subscription)
            .join(UserSettings, UserSettings.user_id == User.id)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                User.is_active == True,
                Subscription.status.in_(["active", "trialing"]),
            )
        )
        rows = result.all()

        enqueued = 0
        for user, settings, subscription in rows:
            # Check if this user's schedule_hour (in their timezone) maps to current UTC hour
            user_utc_hour = _utc_hour_for_user(settings.schedule_hour, settings.timezone)
            if user_utc_hour != current_utc_hour:
                continue

            # Check if user already has a briefing from the last 20 hours (prevent duplicates)
            cutoff = datetime.now(UTC) - timedelta(hours=DUPLICATE_BRIEFING_HOURS)
            recent = await db.execute(
                select(Briefing)
                .where(
                    Briefing.user_id == user.id,
                    Briefing.created_at >= cutoff,
                )
                .limit(1)
            )
            if recent.scalar_one_or_none():
                logger.debug(f"User {user.id} already has recent briefing, skipping")
                continue

            # Enqueue pipeline job
            if redis:
                await redis.enqueue_job("run_user_pipeline_job", user.id)
                enqueued += 1
                logger.info(f"Enqueued pipeline for user {user.id} (@{user.x_username})")

        logger.info(f"Scheduler: checked {len(rows)} users, enqueued {enqueued} pipeline jobs")
