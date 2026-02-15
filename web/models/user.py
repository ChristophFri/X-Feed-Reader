"""User model — stores X OAuth credentials and profile."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.utils import now_utc
from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    x_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    x_username: Mapped[str] = mapped_column(String(64), nullable=False)
    x_display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    x_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    # Relationships
    subscription: Mapped["Subscription | None"] = relationship(back_populates="user", uselist=False)
    settings: Mapped["UserSettings | None"] = relationship(back_populates="user", uselist=False)
    tweets: Mapped[list["Tweet"]] = relationship(back_populates="user")
    scrape_runs: Mapped[list["ScrapeRun"]] = relationship(back_populates="user")
    briefings: Mapped[list["Briefing"]] = relationship(back_populates="user")
