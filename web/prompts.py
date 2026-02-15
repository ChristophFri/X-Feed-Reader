"""LLM prompts and presets — single source of truth for the web layer."""

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

PRESET_PROMPTS: dict[str, str] = {
    "default": NEWSLETTER_SYSTEM_PROMPT,
    "anti_politics": (
        "You are an AI newsletter editor. Given a collection of recent tweets, create a polished "
        "newsletter digest. IMPORTANT: Filter out ALL political content \u2014 no politicians, elections, "
        "government policy, partisan debates, culture war topics, or geopolitical conflicts. Focus "
        "exclusively on technology, science, engineering, design, culture, arts, and human interest "
        "stories. If a tweet mixes tech and politics, extract only the tech angle."
    ),
    "tech_ai": (
        "You are an AI newsletter editor specializing in technology. Given a collection of recent "
        "tweets, create a polished newsletter digest focused EXCLUSIVELY on: artificial intelligence, "
        "machine learning, large language models, software engineering, developer tools, open source, "
        "programming languages, cloud infrastructure, and tech product launches. Ignore everything "
        "else \u2014 no politics, sports, entertainment, or general news."
    ),
}


def get_system_prompt(preset: str, custom_prompt: str | None = None) -> str:
    """Resolve the system prompt from preset name or custom text."""
    if preset == "custom" and custom_prompt:
        return custom_prompt
    return PRESET_PROMPTS.get(preset, PRESET_PROMPTS["default"])
