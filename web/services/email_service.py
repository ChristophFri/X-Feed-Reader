"""Email delivery via Resend API."""

import asyncio
import logging

import resend

from web.config import get_settings

logger = logging.getLogger(__name__)


async def send_briefing_email(
    to_email: str,
    subject: str,
    html_body: str,
) -> bool:
    """Send a briefing email via Resend.

    Returns True on success, False on failure.
    """
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured — skipping email")
        return False

    try:
        await asyncio.to_thread(
            resend.Emails.send,
            {
                "from": settings.email_from,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            },
        )
        logger.info("Briefing email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False
