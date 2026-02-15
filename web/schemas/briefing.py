"""Briefing-related Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel


class BriefingSummary(BaseModel):
    id: int
    tweet_count: int
    llm_provider: str
    prompt_preset: str
    delivered_email: bool
    delivered_telegram: bool
    delivery_error: str | None = None
    created_at: datetime


class BriefingDetail(BriefingSummary):
    content: str
