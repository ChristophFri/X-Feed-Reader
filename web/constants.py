"""Centralized application constants — single source of truth for hardcoded values."""

# --- Session ---
COOKIE_NAME = "xfeed_session"

# --- OAuth ---
OAUTH_STATE_TTL = 600  # seconds (10 min)
DEFAULT_TOKEN_EXPIRY = 7200  # seconds (2 hours)

# --- Twitter API URLs ---
TWITTER_AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
TWITTER_USER_ME_URL = "https://api.twitter.com/2/users/me"
TWITTER_TIMELINE_URL = "https://api.twitter.com/2/users/{user_id}/timelines/reverse_chronological"
TWITTER_SCOPES = "tweet.read users.read offline.access"

# --- Twitter API Fields ---
TWEET_FIELDS = "id,text,created_at,public_metrics,referenced_tweets,entities"
USER_FIELDS = "id,name,username"
EXPANSIONS = "author_id,referenced_tweets.id,referenced_tweets.id.author_id"
MEDIA_FIELDS = "url,preview_image_url"
TWITTER_API_MAX_RESULTS = 100
TOKEN_REFRESH_THRESHOLD_MINUTES = 5

# --- Anthropic ---
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
LMSTUDIO_PLACEHOLDER_KEY = "lm-studio"

# --- HTTP Client ---
HTTP_TOTAL_TIMEOUT = 180  # seconds
HTTP_CONNECT_TIMEOUT = 10  # seconds
TWITTER_API_TIMEOUT = 30  # seconds
TWITTER_CONNECTION_CHECK_TIMEOUT = 10  # seconds

# --- Worker ---
ARQ_MAX_JOBS = 10
ARQ_JOB_TIMEOUT = 600  # seconds (10 min)

# --- Scheduler ---
DUPLICATE_BRIEFING_HOURS = 20  # hours window

# --- Pagination ---
BRIEFINGS_PER_PAGE = 10

# --- HTML Sanitization ---
ALLOWED_HTML_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "a", "strong", "em", "code", "pre",
    "table", "thead", "tbody", "tr", "th", "td",
    "blockquote", "br", "hr", "img", "div", "span",
}
