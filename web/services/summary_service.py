"""Multi-provider LLM summarization — uses centralized prompts and constants."""

import logging
from typing import Any

import httpx

from src.summarizer import _format_tweets_for_prompt
from web.config import get_settings
from web.constants import ANTHROPIC_API_URL, ANTHROPIC_API_VERSION, LMSTUDIO_PLACEHOLDER_KEY
from web.http_client import get_http_client
from web.prompts import NEWSLETTER_USER_PROMPT, get_system_prompt

logger = logging.getLogger(__name__)


class SummaryGenerationError(Exception):
    """Raised when LLM summary generation fails."""


async def generate_summary(
    tweets: list[dict[str, Any]],
    provider: str = "openai",
    model: str | None = None,
    preset: str = "default",
    custom_prompt: str | None = None,
    max_tweets: int = 50,
) -> str:
    """Generate a newsletter summary using the specified LLM provider.

    All providers use the OpenAI-compatible chat completions format,
    except Anthropic which needs a thin adapter.

    Raises SummaryGenerationError on failure.
    """
    if not tweets:
        return "No tweets found in the specified time period."

    system_prompt = get_system_prompt(preset, custom_prompt)
    tweets_json = _format_tweets_for_prompt(tweets, limit=max_tweets)
    user_prompt = NEWSLETTER_USER_PROMPT.format(tweets_json=tweets_json)

    settings = get_settings()

    if provider == "openai" or provider == "lmstudio":
        return await _call_openai_compatible(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            base_url=settings.openai_base_url if provider == "openai" else settings.lmstudio_url,
            api_key=settings.openai_api_key if provider == "openai" else LMSTUDIO_PLACEHOLDER_KEY,
            model=model or (settings.openai_model if provider == "openai" else None),
        )
    elif provider == "anthropic":
        return await _call_anthropic(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            api_key=settings.anthropic_api_key,
            model=model or settings.anthropic_model,
        )
    else:
        raise SummaryGenerationError(f"Unknown LLM provider: {provider}")


async def _call_openai_compatible(
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    api_key: str,
    model: str | None = None,
) -> str:
    """Call an OpenAI-compatible chat completions endpoint (OpenAI, LM Studio)."""
    settings = get_settings()
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    # Handle case where base_url already includes /v1
    if "/v1/v1/" in url:
        url = f"{base_url.rstrip('/')}/chat/completions"

    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "stream": False,
    }
    if model:
        payload["model"] = model

    headers = {"Content-Type": "application/json"}
    if api_key and api_key != LMSTUDIO_PLACEHOLDER_KEY:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        client = get_http_client()
        resp = await client.post(url, json=payload, headers=headers, timeout=settings.llm_timeout)
        resp.raise_for_status()
        data = resp.json()

        if data.get("choices") and len(data["choices"]) > 0:
            content = data["choices"][0].get("message", {}).get("content", "")
            if content:
                return content

        raise SummaryGenerationError("LLM returned empty response")
    except httpx.HTTPStatusError as e:
        logger.error("LLM HTTP error: %s - %s", e.response.status_code, e.response.text[:500])
        raise SummaryGenerationError(f"LLM error: HTTP {e.response.status_code}") from e
    except SummaryGenerationError:
        raise
    except Exception as e:
        logger.error("LLM error: %s", e)
        raise SummaryGenerationError(f"Error generating summary: {e}") from e


async def _call_anthropic(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
) -> str:
    """Call the Anthropic Messages API."""
    settings = get_settings()
    payload = {
        "model": model,
        "max_tokens": settings.llm_max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "Content-Type": "application/json",
    }

    try:
        client = get_http_client()
        resp = await client.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=settings.llm_timeout)
        resp.raise_for_status()
        data = resp.json()

        if data.get("content") and len(data["content"]) > 0:
            text = data["content"][0].get("text", "")
            if text:
                return text

        raise SummaryGenerationError("Anthropic returned empty response")
    except httpx.HTTPStatusError as e:
        logger.error("Anthropic HTTP error: %s - %s", e.response.status_code, e.response.text[:500])
        raise SummaryGenerationError(f"Anthropic error: HTTP {e.response.status_code}") from e
    except SummaryGenerationError:
        raise
    except Exception as e:
        logger.error("Anthropic error: %s", e)
        raise SummaryGenerationError(f"Error generating summary: {e}") from e
