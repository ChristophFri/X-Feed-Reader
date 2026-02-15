"""Web application configuration via environment variables."""

import base64
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

_INSECURE_DEFAULTS = {"change-me-in-production", "change-me-jwt-secret", "change-me-fernet-key"}


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # --- App ---
    app_name: str = "X Feed Reader"
    app_url: str = "http://localhost:8000"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://xfeed:xfeed@localhost:5432/xfeed"

    @field_validator("database_url", mode="before")
    @classmethod
    def _fix_db_scheme(cls, v: str) -> str:
        """Railway provides postgresql:// but asyncpg needs postgresql+asyncpg://."""
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # --- Redis ---
    redis_url: str = "redis://localhost:6379"

    # --- JWT ---
    jwt_secret: str = "change-me-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # --- Encryption (Fernet) ---
    fernet_key: str = "change-me-fernet-key"

    # --- X / Twitter OAuth 2.0 ---
    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    twitter_redirect_uri: str = "http://localhost:8000/auth/callback"

    # --- Stripe ---
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""

    # --- Resend (email) ---
    resend_api_key: str = ""
    email_from: str = "briefings@xfeedreader.com"

    # --- LLM defaults ---
    default_llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    lmstudio_url: str = "http://localhost:1234"

    # --- LLM tuning ---
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_timeout: int = 180

    # --- Feature flags ---
    disable_playwright: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        """Refuse to start with insecure default secrets in production."""
        if self.debug:
            return self

        insecure = []
        if self.secret_key in _INSECURE_DEFAULTS:
            insecure.append("SECRET_KEY")
        if self.jwt_secret in _INSECURE_DEFAULTS:
            insecure.append("JWT_SECRET")
        if self.fernet_key in _INSECURE_DEFAULTS:
            insecure.append("FERNET_KEY")

        if insecure:
            raise ValueError(
                f"Insecure default values detected for: {', '.join(insecure)}. "
                "Set these to secure random values via environment variables or .env file."
            )

        # Validate Fernet key format (must be 32 url-safe base64 bytes)
        try:
            key_bytes = base64.urlsafe_b64decode(self.fernet_key)
            if len(key_bytes) != 32:
                raise ValueError("decoded key is not 32 bytes")
        except Exception:
            raise ValueError(
                "FERNET_KEY is not a valid Fernet key. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
