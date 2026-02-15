"""Tweet model — multi-tenant version of src/database.py Tweet."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.utils import now_utc
from .base import Base


class Tweet(Base):
    __tablename__ = "web_tweets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tweet_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    author_handle: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    author_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retweets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    replies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_retweet: Mapped[bool] = mapped_column(Boolean, default=False)
    original_author: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_to_handle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        UniqueConstraint("tweet_id", "user_id", name="uq_tweet_user"),
    )

    user: Mapped["User"] = relationship(back_populates="tweets")
