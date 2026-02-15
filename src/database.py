"""Database layer using SQLAlchemy for storing tweets and scrape runs."""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, create_engine, func, case
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from .utils import now_utc

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


class Tweet(Base):
    """Model representing a scraped tweet."""

    __tablename__ = "tweets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    author_handle: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    author_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retweets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    replies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_retweet: Mapped[bool] = mapped_column(Boolean, default=False)
    original_author: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_to_handle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert tweet to dictionary."""
        return {
            "id": self.id,
            "author_handle": self.author_handle,
            "author_name": self.author_name,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "likes": self.likes,
            "retweets": self.retweets,
            "replies": self.replies,
            "media_urls": self.media_urls,
            "is_retweet": self.is_retweet,
            "original_author": self.original_author,
            "is_reply": self.is_reply,
            "reply_to_handle": self.reply_to_handle,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }


class ScrapeRun(Base):
    """Model representing a scraping run."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tweets_found: Mapped[int] = mapped_column(Integer, default=0)
    tweets_new: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(128), default="running")


class Database:
    """Database manager for X Feed Reader."""

    def __init__(self, db_path: str = "data/x_feed.db"):
        """
        Initialize database connection.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path

        # Ensure parent directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

    def init_db(self) -> None:
        """Create all tables if they don't exist, and migrate old schemas."""
        try:
            self._migrate_drop_removed_columns()
            Base.metadata.create_all(self.engine)
            logger.debug("Database tables initialized")
        except SQLAlchemyError as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _migrate_drop_removed_columns(self) -> None:
        """Drop columns removed in v0.4.0 from existing databases."""
        import sqlite3

        removed = ["is_read", "summary", "reply_to_content"]
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("PRAGMA table_info(tweets)")
            existing = {row[1] for row in cursor.fetchall()}
            for col in removed:
                if col in existing:
                    # Drop any indexes referencing this column first
                    idx_cursor = conn.execute("PRAGMA index_list(tweets)")
                    for idx_row in idx_cursor.fetchall():
                        idx_name = idx_row[1]
                        info_cursor = conn.execute(f"PRAGMA index_info({idx_name})")
                        idx_cols = [r[2] for r in info_cursor.fetchall()]
                        if col in idx_cols:
                            conn.execute(f"DROP INDEX IF EXISTS {idx_name}")
                    conn.execute(f"ALTER TABLE tweets DROP COLUMN {col}")
                    logger.info(f"Dropped legacy column tweets.{col}")
            conn.commit()
        except sqlite3.OperationalError:
            # Table doesn't exist yet (fresh database) — nothing to migrate
            pass
        finally:
            conn.close()

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def add_tweets(self, tweets: list[dict[str, Any]]) -> int:
        """
        Add tweets to the database, ignoring duplicates.

        Args:
            tweets: List of tweet dictionaries with tweet data.

        Returns:
            Number of new tweets added.
        """
        new_count = 0

        try:
            with self.get_session() as session:
                for tweet_data in tweets:
                    tweet_id = tweet_data.get("id")
                    if not tweet_id:
                        logger.debug("Skipping tweet without ID")
                        continue

                    existing = session.get(Tweet, tweet_id)
                    if existing:
                        logger.debug(f"Tweet {tweet_id} already exists, skipping")
                        continue

                    tweet = Tweet(
                        id=tweet_id,
                        author_handle=tweet_data.get("author_handle"),
                        author_name=tweet_data.get("author_name"),
                        content=tweet_data.get("content"),
                        timestamp=tweet_data.get("timestamp"),
                        likes=tweet_data.get("likes"),
                        retweets=tweet_data.get("retweets"),
                        replies=tweet_data.get("replies"),
                        media_urls=tweet_data.get("media_urls"),
                        is_retweet=tweet_data.get("is_retweet", False),
                        original_author=tweet_data.get("original_author"),
                        is_reply=tweet_data.get("is_reply", False),
                        reply_to_handle=tweet_data.get("reply_to_handle"),
                        scraped_at=now_utc(),
                    )
                    session.add(tweet)
                    new_count += 1

                session.commit()
                logger.info(f"Added {new_count} new tweets to database")

        except SQLAlchemyError as e:
            logger.error(f"Failed to add tweets: {e}")
            raise

        return new_count

    def tweet_exists(self, tweet_id: str) -> bool:
        """
        Check if a tweet already exists in the database.

        Args:
            tweet_id: The tweet ID to check.

        Returns:
            True if tweet exists, False otherwise.
        """
        try:
            with self.get_session() as session:
                return session.get(Tweet, tweet_id) is not None
        except SQLAlchemyError as e:
            logger.error(f"Failed to check tweet existence: {e}")
            return False

    def get_tweets_since(self, since_hours: int = 24) -> list[Tweet]:
        """
        Get tweets from the last X hours.

        Args:
            since_hours: Number of hours to look back.

        Returns:
            List of Tweet objects.
        """
        cutoff = now_utc() - timedelta(hours=since_hours)

        try:
            with self.get_session() as session:
                tweets = (
                    session.query(Tweet)
                    .filter(Tweet.scraped_at >= cutoff)
                    .order_by(Tweet.timestamp.desc())
                    .all()
                )
                session.expunge_all()
                return tweets
        except SQLAlchemyError as e:
            logger.error(f"Failed to get tweets: {e}")
            return []

    def get_stats(self) -> dict[str, Any]:
        """
        Get database statistics in a single optimized query.

        Returns:
            Dictionary with stats: total_tweets, last_scrape, tweets_today.
        """
        today_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)

        try:
            with self.get_session() as session:
                # Combined query for tweet stats
                stats = session.query(
                    func.count(Tweet.id).label("total"),
                    func.sum(case((Tweet.scraped_at >= today_start, 1), else_=0)).label("today"),
                ).one()

                total_tweets = stats.total or 0
                tweets_today = stats.today or 0

                # Get last scrape time
                last_run = (
                    session.query(ScrapeRun)
                    .order_by(ScrapeRun.started_at.desc())
                    .first()
                )
                last_scrape = last_run.started_at if last_run else None

                return {
                    "total_tweets": total_tweets,
                    "last_scrape": last_scrape.isoformat() if last_scrape else None,
                    "tweets_today": tweets_today,
                }
        except SQLAlchemyError as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "total_tweets": 0,
                "last_scrape": None,
                "tweets_today": 0,
            }

    def cleanup_old_tweets(self, keep_count: int = 100) -> int:
        """
        Delete old tweets, keeping only the most recent ones.

        Args:
            keep_count: Number of most recent tweets to keep.

        Returns:
            Number of tweets deleted.
        """
        try:
            with self.get_session() as session:
                # Get the total count
                total = session.query(func.count(Tweet.id)).scalar() or 0

                if total <= keep_count:
                    logger.debug(f"Only {total} tweets in database, no cleanup needed")
                    return 0

                # Get the scraped_at timestamp of the Nth most recent tweet
                cutoff_tweet = (
                    session.query(Tweet.scraped_at)
                    .order_by(Tweet.scraped_at.desc())
                    .offset(keep_count - 1)
                    .limit(1)
                    .scalar()
                )

                if not cutoff_tweet:
                    return 0

                # Delete all tweets older than the cutoff
                deleted = (
                    session.query(Tweet)
                    .filter(Tweet.scraped_at < cutoff_tweet)
                    .delete(synchronize_session=False)
                )

                session.commit()
                logger.info(f"Cleaned up {deleted} old tweets, keeping {keep_count} most recent")
                return deleted

        except SQLAlchemyError as e:
            logger.error(f"Failed to cleanup old tweets: {e}")
            raise

    def log_scrape_run(
        self,
        started_at: datetime,
        finished_at: datetime | None,
        tweets_found: int,
        tweets_new: int,
        status: str,
    ) -> int:
        """
        Log a scraping run.

        Args:
            started_at: When the scrape started.
            finished_at: When the scrape finished.
            tweets_found: Total tweets found.
            tweets_new: New tweets added.
            status: Status of the run (e.g., "completed", "failed").

        Returns:
            The ID of the created scrape run.
        """
        try:
            with self.get_session() as session:
                run = ScrapeRun(
                    started_at=started_at,
                    finished_at=finished_at,
                    tweets_found=tweets_found,
                    tweets_new=tweets_new,
                    status=status,
                )
                session.add(run)
                session.commit()
                logger.debug(f"Logged scrape run: {tweets_found} found, {tweets_new} new")
                return run.id
        except SQLAlchemyError as e:
            logger.error(f"Failed to log scrape run: {e}")
            raise


def init_db(db_path: str = "data/x_feed.db") -> Database:
    """
    Initialize the database and return a Database instance.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Initialized Database instance.
    """
    db = Database(db_path)
    db.init_db()
    return db
