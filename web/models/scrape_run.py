"""ScrapeRun model — multi-tenant version of src/database.py ScrapeRun."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.utils import now_utc
from .base import Base


class ScrapeRun(Base):
    __tablename__ = "web_scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tweets_found: Mapped[int] = mapped_column(Integer, default=0)
    tweets_new: Mapped[int] = mapped_column(Integer, default=0)
    feed_source: Mapped[str] = mapped_column(String(16), default="api")
    status: Mapped[str] = mapped_column(String(128), default="running")

    user: Mapped["User"] = relationship(back_populates="scrape_runs")
