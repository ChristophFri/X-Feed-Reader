"""UserSettings model — per-user preferences for feed, LLM, delivery."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    feed_source: Mapped[str] = mapped_column(String(16), default="api")
    max_tweets: Mapped[int] = mapped_column(Integer, default=100)
    summary_hours: Mapped[int] = mapped_column(Integer, default=24)
    prompt_preset: Mapped[str] = mapped_column(String(32), default="default")
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String(32), default="openai")
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schedule_hour: Mapped[int] = mapped_column(Integer, default=8)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    delivery_email: Mapped[bool] = mapped_column(Boolean, default=True)
    delivery_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_bot_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship(back_populates="settings")
