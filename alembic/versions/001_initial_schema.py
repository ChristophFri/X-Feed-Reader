"""Initial schema — users, subscriptions, settings, tweets, scrape_runs, briefings.

Revision ID: 001
Revises: None
Create Date: 2026-02-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("x_user_id", sa.String(64), nullable=False),
        sa.Column("x_username", sa.String(64), nullable=False),
        sa.Column("x_display_name", sa.String(128), nullable=True),
        sa.Column("x_access_token", sa.Text(), nullable=True),
        sa.Column("x_refresh_token", sa.Text(), nullable=True),
        sa.Column("x_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("x_user_id"),
        sa.UniqueConstraint("stripe_customer_id"),
    )

    # --- subscriptions ---
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(64), nullable=False),
        sa.Column("stripe_price_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("stripe_subscription_id"),
    )

    # --- user_settings ---
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("feed_source", sa.String(16), server_default="api", nullable=False),
        sa.Column("max_tweets", sa.Integer(), server_default="100", nullable=False),
        sa.Column("summary_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("prompt_preset", sa.String(32), server_default="default", nullable=False),
        sa.Column("custom_prompt", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.String(32), server_default="openai", nullable=False),
        sa.Column("llm_model", sa.String(128), nullable=True),
        sa.Column("schedule_hour", sa.Integer(), server_default="8", nullable=False),
        sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("delivery_email", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("delivery_telegram", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("telegram_bot_token", sa.Text(), nullable=True),
        sa.Column("telegram_chat_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # --- web_tweets ---
    op.create_table(
        "web_tweets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tweet_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("author_handle", sa.String(64), nullable=True),
        sa.Column("author_name", sa.String(128), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("retweets", sa.Integer(), nullable=True),
        sa.Column("replies", sa.Integer(), nullable=True),
        sa.Column("media_urls", sa.JSON(), nullable=True),
        sa.Column("is_retweet", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("original_author", sa.String(64), nullable=True),
        sa.Column("is_reply", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reply_to_handle", sa.String(64), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tweet_id", "user_id", name="uq_tweet_user"),
    )
    op.create_index("ix_web_tweets_tweet_id", "web_tweets", ["tweet_id"])
    op.create_index("ix_web_tweets_user_id", "web_tweets", ["user_id"])
    op.create_index("ix_web_tweets_author_handle", "web_tweets", ["author_handle"])
    op.create_index("ix_web_tweets_timestamp", "web_tweets", ["timestamp"])

    # --- web_scrape_runs ---
    op.create_table(
        "web_scrape_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tweets_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tweets_new", sa.Integer(), server_default="0", nullable=False),
        sa.Column("feed_source", sa.String(16), server_default="api", nullable=False),
        sa.Column("status", sa.String(128), server_default="running", nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_web_scrape_runs_user_id", "web_scrape_runs", ["user_id"])

    # --- briefings ---
    op.create_table(
        "briefings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tweet_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("llm_provider", sa.String(32), nullable=False),
        sa.Column("prompt_preset", sa.String(32), server_default="default", nullable=False),
        sa.Column("delivered_email", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("delivered_telegram", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("delivery_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_briefings_user_id", "briefings", ["user_id"])


def downgrade() -> None:
    op.drop_table("briefings")
    op.drop_table("web_scrape_runs")
    op.drop_table("web_tweets")
    op.drop_table("user_settings")
    op.drop_table("subscriptions")
    op.drop_table("users")
