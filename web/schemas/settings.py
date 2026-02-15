"""Settings-related Pydantic schemas."""

from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator


class SettingsUpdate(BaseModel):
    feed_source: Literal["api", "scraper"] | None = None
    max_tweets: int | None = Field(None, ge=10, le=500)
    summary_hours: int | None = Field(None, ge=1, le=168)
    prompt_preset: Literal["default", "anti_politics", "tech_ai", "custom"] | None = None
    custom_prompt: str | None = Field(None, max_length=2000)
    llm_provider: Literal["openai", "anthropic", "lmstudio"] | None = None
    llm_model: str | None = None
    schedule_hour: int | None = Field(None, ge=0, le=23)
    timezone: str | None = None
    delivery_email: bool | None = None
    delivery_telegram: bool | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (KeyError, ValueError):
            raise ValueError(f"Invalid timezone: {v}")
        return v
