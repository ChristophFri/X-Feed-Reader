"""Stripe subscription management — checkout, portal, gating."""

import asyncio
import logging
from datetime import datetime, UTC

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.config import get_settings
from web.models.subscription import Subscription
from web.models.user import User

logger = logging.getLogger(__name__)


def init_stripe() -> None:
    """Set the Stripe API key from settings. Call once at startup."""
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key


def _get_period_timestamps(stripe_sub) -> tuple[int | None, int | None]:
    """Extract current_period_start/end, handling Stripe API version differences.

    Newer API versions (2024-06-20+) moved these fields to items.data[0].
    """
    # Try top-level first (older API versions / webhook event data)
    try:
        return stripe_sub["current_period_start"], stripe_sub["current_period_end"]
    except (KeyError, TypeError):
        pass
    # Try items.data[0] (newer API versions)
    try:
        item = stripe_sub["items"]["data"][0]
        return item["current_period_start"], item["current_period_end"]
    except (KeyError, TypeError, IndexError):
        pass
    return None, None


def _subscription_from_stripe_data(
    stripe_sub: dict, user_id: int
) -> Subscription:
    """Create a Subscription ORM object from Stripe subscription data."""
    period_start, period_end = _get_period_timestamps(stripe_sub)
    return Subscription(
        user_id=user_id,
        stripe_subscription_id=stripe_sub["id"] if isinstance(stripe_sub, dict) else stripe_sub.id,
        stripe_price_id=stripe_sub["items"]["data"][0]["price"]["id"],
        status=stripe_sub["status"],
        current_period_start=datetime.fromtimestamp(period_start, tz=UTC) if period_start else None,
        current_period_end=datetime.fromtimestamp(period_end, tz=UTC) if period_end else None,
        cancel_at_period_end=stripe_sub.get("cancel_at_period_end", False),
    )


def _update_subscription_from_stripe(sub: Subscription, stripe_sub: dict) -> None:
    """Update an existing Subscription ORM object from Stripe subscription data."""
    period_start, period_end = _get_period_timestamps(stripe_sub)
    sub.stripe_subscription_id = stripe_sub["id"] if isinstance(stripe_sub, dict) else stripe_sub.id
    sub.stripe_price_id = stripe_sub["items"]["data"][0]["price"]["id"]
    sub.status = stripe_sub["status"]
    if period_start:
        sub.current_period_start = datetime.fromtimestamp(period_start, tz=UTC)
    if period_end:
        sub.current_period_end = datetime.fromtimestamp(period_end, tz=UTC)
    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)


async def create_checkout_session(user: User, db: AsyncSession) -> str:
    """Create a Stripe Checkout session and return the URL."""
    settings = get_settings()

    # Ensure user has a Stripe customer
    if not user.stripe_customer_id:
        customer = await asyncio.to_thread(
            stripe.Customer.create,
            metadata={"user_id": str(user.id), "x_username": user.x_username},
            email=user.email,
        )
        user.stripe_customer_id = customer.id
        await db.commit()

    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        customer=user.stripe_customer_id,
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=f"{settings.app_url}/app/billing?success=true",
        cancel_url=f"{settings.app_url}/app/billing?canceled=true",
        metadata={"user_id": str(user.id)},
    )
    return session.url


async def create_portal_session(user: User) -> str:
    """Create a Stripe Customer Portal session and return the URL."""
    settings = get_settings()

    if not user.stripe_customer_id:
        raise ValueError("User has no Stripe customer ID")

    session = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=user.stripe_customer_id,
        return_url=f"{settings.app_url}/app/billing",
    )
    return session.url


async def is_subscription_active(db: AsyncSession, user_id: int) -> bool:
    """Check if a user has an active (or grace-period) subscription."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return False

    if sub.status in ("active", "trialing"):
        return True

    # Grace period: canceled but still within paid period
    if sub.status == "canceled" and sub.current_period_end:
        return sub.current_period_end > datetime.now(UTC)

    return False


async def handle_checkout_completed(session_data: dict, db: AsyncSession) -> None:
    """Handle checkout.session.completed webhook event (idempotent)."""
    user_id = int(session_data["metadata"]["user_id"])
    subscription_id = session_data["subscription"]

    stripe_sub = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)

    # Check by stripe_subscription_id first for idempotency
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    sub = result.scalar_one_or_none()

    if sub:
        _update_subscription_from_stripe(sub, stripe_sub)
    else:
        # Also check if user already has a subscription (update rather than duplicate)
        result = await db.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            _update_subscription_from_stripe(sub, stripe_sub)
        else:
            sub = _subscription_from_stripe_data(stripe_sub, user_id)
            db.add(sub)

    await db.commit()


async def handle_invoice_paid(invoice_data: dict, db: AsyncSession) -> None:
    """Handle invoice.paid webhook — update period and ensure active."""
    subscription_id = invoice_data.get("subscription")
    if not subscription_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    stripe_sub = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)
    period_start, period_end = _get_period_timestamps(stripe_sub)
    sub.status = "active"
    if period_start:
        sub.current_period_start = datetime.fromtimestamp(period_start, tz=UTC)
    if period_end:
        sub.current_period_end = datetime.fromtimestamp(period_end, tz=UTC)
    await db.commit()


async def handle_invoice_payment_failed(invoice_data: dict, db: AsyncSession) -> None:
    subscription_id = invoice_data.get("subscription")
    if not subscription_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = "past_due"
        await db.commit()


async def handle_subscription_updated(sub_data: dict, db: AsyncSession) -> None:
    subscription_id = sub_data["id"]
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    sub.status = sub_data["status"]
    sub.cancel_at_period_end = sub_data.get("cancel_at_period_end", False)
    period_start, period_end = _get_period_timestamps(sub_data)
    if period_start:
        sub.current_period_start = datetime.fromtimestamp(period_start, tz=UTC)
    if period_end:
        sub.current_period_end = datetime.fromtimestamp(period_end, tz=UTC)
    await db.commit()


async def handle_subscription_deleted(sub_data: dict, db: AsyncSession) -> None:
    subscription_id = sub_data["id"]
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = "canceled"
        await db.commit()
