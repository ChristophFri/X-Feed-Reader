"""Summarization logic for tweets using local LM Studio."""

import json
import logging
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

# Default LM Studio server URL
DEFAULT_LMSTUDIO_URL = "http://localhost:1234"

# Newsletter editor system prompt
NEWSLETTER_SYSTEM_PROMPT = """You are an AI newsletter editor. Given a collection of recent tweets about AI/tech, create a polished newsletter digest."""

NEWSLETTER_USER_PROMPT = """## Input
{tweets_json}

## Instructions

1. **Analyze & Categorize**: Group tweets by theme (Research, Product Launches, Industry News, Drama/Controversy, Insights)

2. **Identify the Top Story**: Pick the single most impactful/discussed topic. Write 3-4 sentences explaining what happened and why it matters.

3. **Create Headlines Section**: Select 5-8 other noteworthy items. For each:
   - Write a compelling one-line summary
   - Include the source: [@handle](tweet_url)
   - Add a brief "why it matters" (1 sentence)

4. **Spot Trends**: If multiple tweets discuss the same topic, synthesize them into a single insight with multiple sources.

5. **Filter Noise**: Ignore promotional spam, low-engagement hot takes, and off-topic content.

6. **Handle Replies**: Some tweets have `is_reply: true` with `original_tweet` showing what they're responding to. Use this context to understand the discussion. When summarizing replies, include the original context to make the story clear.

## Output Format

# 🔥 Top Story
**[Headline]**
[3-4 sentence summary with context and implications]
Source: [@handle](url)

---

# 📰 What Else Happened

### [Category Name]
- **[Headline]** — [One sentence summary] ([Source](url))
- **[Headline]** — [One sentence summary] ([Source](url))

### [Category Name]
...

---

# 📊 Emerging Pattern
[If you notice 3+ tweets about the same trend, synthesize here with multiple source links]

---

# 💡 One to Watch
[Single forward-looking insight or prediction based on the tweets]"""


def _format_tweets_for_prompt(tweets: list[dict[str, Any]], limit: int = 50) -> str:
    """
    Format tweets as JSON for the newsletter prompt.

    Args:
        tweets: List of tweet dictionaries.
        limit: Maximum number of tweets to include (default 50 for context limits).

    Returns:
        JSON string of formatted tweets.
    """
    formatted = []
    for tweet in tweets[:limit]:
        tweet_id = tweet.get("id") or ""
        author = tweet.get("author_handle") or "unknown"
        content = tweet.get("content") or ""
        likes = tweet.get("likes") or 0
        retweets = tweet.get("retweets") or 0
        timestamp = tweet.get("timestamp") or ""
        is_reply = tweet.get("is_reply", False)
        reply_to_handle = tweet.get("reply_to_handle")

        if content:
            tweet_entry = {
                "author": f"@{author}",
                "content": content[:300],  # Shorter content for context limits
                "url": f"https://x.com/{author}/status/{tweet_id}" if tweet_id else None,
                "likes": likes,
                "retweets": retweets,
                "timestamp": str(timestamp) if timestamp else None,
            }

            # Add reply context if this is a reply
            if is_reply:
                tweet_entry["is_reply"] = True
                if reply_to_handle:
                    tweet_entry["replying_to"] = f"@{reply_to_handle}"

            formatted.append(tweet_entry)

    return json.dumps(formatted, ensure_ascii=False)


def generate_summary_lmstudio(
    tweets: list[dict[str, Any]],
    base_url: str = DEFAULT_LMSTUDIO_URL,
    model: str | None = None,
    max_tweets: int = 50,
) -> str:
    """
    Generate a newsletter-style summary using a local LM Studio server.

    Args:
        tweets: List of tweet dictionaries.
        base_url: LM Studio server URL (default: http://localhost:1234).
        model: Model identifier (optional, LM Studio uses loaded model by default).
        max_tweets: Maximum number of tweets to include in prompt.

    Returns:
        LLM-generated newsletter digest.

    Note:
        Falls back to error message if API call fails.
        Uses OpenAI-compatible chat completions endpoint.
    """
    if not tweets:
        return "No tweets found in the specified time period."

    tweets_json = _format_tweets_for_prompt(tweets, limit=max_tweets)
    prompt = NEWSLETTER_USER_PROMPT.format(tweets_json=tweets_json)

    # Build request payload
    payload = {
        "messages": [
            {
                "role": "system",
                "content": NEWSLETTER_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
        "stream": False,
    }

    if model:
        payload["model"] = model

    try:
        logger.info(f"Generating LM Studio newsletter summary from {base_url}...")

        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))

        if result.get("choices") and len(result["choices"]) > 0:
            message = result["choices"][0].get("message", {})
            content = message.get("content", "")
            if content:
                logger.info("LM Studio newsletter summary generated successfully")
                return content

        logger.warning("LM Studio returned empty response")
        return "No summary generated."

    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        logger.error(f"HTTP error from LM Studio: {e.code} - {e.reason} - {error_body}")
        return f"HTTP Error {e.code}: {e.reason}. Details: {error_body[:500]}"
    except urllib.error.URLError as e:
        logger.error(f"Connection error to LM Studio: {e}")
        return f"Connection Error: Could not connect to LM Studio at {base_url}. Is the server running?"
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response from LM Studio: {e}")
        return "Error: Invalid response from LM Studio server."
    except TimeoutError:
        logger.error("LM Studio request timed out")
        return "Error: LM Studio request timed out after 180 seconds."
    except Exception as e:
        logger.error(f"Unexpected error generating summary: {e}")
        return f"Error generating summary: {e}"
