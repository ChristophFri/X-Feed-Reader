"""Delivery dispatcher — sends briefings via email and/or Telegram."""

import asyncio
import logging
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.telegram_notifier import send_summary_to_telegram
from src.utils import calculate_engagement_stats
from web.constants import ALLOWED_HTML_TAGS
from web.db.encryption import decrypt
from web.models.briefing import Briefing
from web.models.user import User
from web.models.user_settings import UserSettings
from web.services.email_service import send_briefing_email

logger = logging.getLogger(__name__)

# Load email template
_template_dir = Path(__file__).parent.parent / "templates" / "email"
_jinja_env = Environment(loader=FileSystemLoader(str(_template_dir)), autoescape=True)


async def deliver_briefing(
    briefing: Briefing,
    db: AsyncSession,
) -> None:
    """Deliver a briefing to all configured channels for the user."""
    # Load user and settings
    user_result = await db.execute(select(User).where(User.id == briefing.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return

    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == briefing.user_id)
    )
    settings = settings_result.scalar_one_or_none()
    if not settings:
        return

    errors = []

    # --- Email delivery ---
    if settings.delivery_email and user.email:
        try:
            import nh3

            raw_html = markdown.markdown(
                briefing.content, extensions=["tables", "fenced_code"]
            )
            html_content = nh3.clean(raw_html, tags=ALLOWED_HTML_TAGS)
            template = _jinja_env.get_template("briefing.html")
            email_html = template.render(
                content=html_content,
                username=user.x_username,
                date=briefing.created_at.strftime("%B %d, %Y"),
                tweet_count=briefing.tweet_count,
            )
            success = await send_briefing_email(
                to_email=user.email,
                subject=f"Your X Feed Briefing — {briefing.created_at.strftime('%b %d')}",
                html_body=email_html,
            )
            if success:
                briefing.delivered_email = True
            else:
                errors.append("Email delivery failed")
        except Exception as e:
            logger.error(f"Email delivery error for user {user.id}: {e}")
            errors.append(f"Email: {e}")

    # --- Telegram delivery ---
    if settings.delivery_telegram and settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            bot_token = decrypt(settings.telegram_bot_token)
            chat_id = settings.telegram_chat_id

            # Run sync Telegram function in thread pool
            success = await asyncio.to_thread(
                send_summary_to_telegram,
                bot_token,
                chat_id,
                briefing.content,
            )
            if success:
                briefing.delivered_telegram = True
            else:
                errors.append("Telegram delivery failed")
        except Exception as e:
            logger.error(f"Telegram delivery error for user {user.id}: {e}")
            errors.append(f"Telegram: {e}")

    if errors:
        briefing.delivery_error = "; ".join(errors)

    await db.commit()
