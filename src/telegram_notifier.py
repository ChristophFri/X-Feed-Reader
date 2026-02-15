"""Telegram notification module for sending summaries."""

import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"
MAX_MESSAGE_LENGTH = 4096  # Telegram message limit


def send_telegram_message(
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: str = "Markdown",
) -> dict[str, Any]:
    """
    Send a message via Telegram Bot API.

    Args:
        bot_token: Telegram bot token.
        chat_id: Chat ID to send the message to.
        message: Message text to send.
        parse_mode: Parse mode for formatting (Markdown or HTML).

    Returns:
        API response as dictionary.

    Raises:
        Exception if sending fails.
    """
    url = f"{TELEGRAM_API_BASE.format(token=bot_token)}/sendMessage"

    # Truncate message if too long
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[: MAX_MESSAGE_LENGTH - 100] + "\n\n... (truncated)"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            logger.info("Telegram message sent successfully")
            return result

    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        logger.error(f"Telegram API error: {e.code} - {error_body}")
        raise Exception(f"Telegram API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        logger.error(f"Connection error to Telegram: {e}")
        raise Exception(f"Connection error to Telegram: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram message: {e}")
        raise


def send_summary_to_telegram(
    bot_token: str,
    chat_id: str,
    summary: str,
    stats: dict[str, Any] | None = None,
) -> bool:
    """
    Send a formatted summary to Telegram.

    Args:
        bot_token: Telegram bot token.
        chat_id: Chat ID to send the message to.
        summary: The summary text to send.
        stats: Optional statistics dictionary.

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Build header
        header = "📰 *X Feed Briefing*\n"
        if stats:
            header += f"_{stats.get('total', 0)} tweets from {stats.get('authors', 0)} authors_\n"
        header += "─" * 20 + "\n\n"

        full_message = header + summary

        # If message is too long, split into multiple messages
        if len(full_message) > MAX_MESSAGE_LENGTH:
            # Send header first
            send_telegram_message(bot_token, chat_id, header, parse_mode="Markdown")

            # Split summary into chunks
            chunks = _split_message(summary, MAX_MESSAGE_LENGTH - 100)
            for i, chunk in enumerate(chunks):
                if i > 0:
                    chunk = "..." + chunk
                send_telegram_message(bot_token, chat_id, chunk, parse_mode="Markdown")
        else:
            send_telegram_message(bot_token, chat_id, full_message, parse_mode="Markdown")

        return True

    except Exception as e:
        logger.error(f"Failed to send summary to Telegram: {e}")
        return False


def _split_message(text: str, max_length: int) -> list[str]:
    """
    Split a long message into chunks.

    Args:
        text: Text to split.
        max_length: Maximum length per chunk.

    Returns:
        List of text chunks.
    """
    chunks = []
    current_chunk = ""

    for line in text.split("\n"):
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += ("\n" if current_chunk else "") + line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
