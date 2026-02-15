"""Admin seed script — creates a local admin user for testing.

Bypasses OAuth and Stripe so you can test the full pipeline locally
with Playwright scraper + LM Studio.

Usage:
    python -m web.admin_seed

Prerequisites:
    1. LM Studio running at localhost:1234
    2. Existing Playwright login session at data/browser-profile (from CLI `xfeed login`)
"""

import asyncio


async def main():
    # Ensure .env is loaded before importing settings
    from dotenv import load_dotenv
    load_dotenv()

    from sqlalchemy import select
    from web.db.session import async_session_factory, engine
    from web.models import Base
    from web.models.user import User
    from web.models.user_settings import UserSettings
    from web.models.subscription import Subscription
    from src.utils import now_utc
    from datetime import timedelta

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.x_user_id == "admin_local"))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Admin user already exists (id={existing.id}, @{existing.x_username})")
            print(f"Login at: http://localhost:8000/app/dashboard")
            print(f"  (session cookie will be set automatically via /auth/admin-login)")
            await engine.dispose()
            return

        # Create admin user
        user = User(
            x_user_id="admin_local",
            x_username="admin",
            x_display_name="Local Admin",
            email="admin@localhost",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        # Create settings — Playwright scraper + LM Studio
        settings = UserSettings(
            user_id=user.id,
            feed_source="scraper",
            max_tweets=50,
            summary_hours=24,
            prompt_preset="default",
            llm_provider="lmstudio",
            schedule_hour=8,
            timezone="UTC",
            delivery_email=False,
            delivery_telegram=False,
        )
        db.add(settings)

        # Create fake active subscription (bypasses Stripe)
        now = now_utc()
        subscription = Subscription(
            user_id=user.id,
            stripe_subscription_id="sub_admin_local",
            stripe_price_id="price_admin_local",
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=365),
            cancel_at_period_end=False,
        )
        db.add(subscription)

        await db.commit()
        await db.refresh(user)

        print(f"Admin user created (id={user.id})")
        print(f"  username:    @admin")
        print(f"  feed source: Playwright scraper (reuses data/browser-profile)")
        print(f"  LLM:         LM Studio at localhost:1234")
        print(f"  subscription: active (fake, 1 year)")
        print()
        print("Next steps:")
        print("  1. Make sure LM Studio is running with a model loaded")
        print("  2. Start the web app:  uvicorn web.app:app --reload")
        print("  3. Open:  http://localhost:8000/auth/admin-login")
        print("     This logs you in as admin and redirects to dashboard.")
        print("  4. Click 'Run Now' to test the full pipeline")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
