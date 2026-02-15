"""ARQ worker — background job processing."""

import logging

from arq import cron
from arq.connections import RedisSettings

from web.config import get_settings
from web.constants import ARQ_JOB_TIMEOUT, ARQ_MAX_JOBS

logger = logging.getLogger(__name__)


async def run_user_pipeline_job(ctx: dict, user_id: int) -> None:
    """ARQ job: run the full pipeline for a single user."""
    from web.db.session import async_session_factory
    from web.services.delivery_service import deliver_briefing
    from web.services.pipeline_service import run_user_pipeline

    async with async_session_factory() as db:
        briefing = await run_user_pipeline(user_id, db)
        if briefing:
            await deliver_briefing(briefing, db)
            logger.info(f"Pipeline + delivery complete for user {user_id}")
        else:
            logger.info(f"No briefing generated for user {user_id}")


async def hourly_scheduler(ctx: dict) -> None:
    """Cron job: every hour, enqueue pipeline runs for due users."""
    from web.scheduler_tasks import enqueue_due_users

    await enqueue_due_users(ctx)


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [run_user_pipeline_job]
    cron_jobs = [cron(hourly_scheduler, minute=0)]  # Every hour at :00

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

    max_jobs = ARQ_MAX_JOBS
    job_timeout = ARQ_JOB_TIMEOUT
