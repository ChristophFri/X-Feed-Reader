"""Dashboard HTML page routes — requires authentication."""

import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from web.constants import ALLOWED_HTML_TAGS, BRIEFINGS_PER_PAGE
from web.db.session import get_db
from web.models.briefing import Briefing
from web.models.scrape_run import ScrapeRun
from web.models.subscription import Subscription
from web.models.tweet import Tweet
from web.models.user import User
from web.services.auth_service import get_current_user
from web.services.user_service import get_or_create_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app", tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = await get_or_create_settings(db, user.id)

    # Subscription status
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscription = sub_result.scalar_one_or_none()

    # Latest briefing
    latest_result = await db.execute(
        select(Briefing)
        .where(Briefing.user_id == user.id)
        .order_by(Briefing.created_at.desc())
        .limit(1)
    )
    latest_briefing = latest_result.scalar_one_or_none()

    # Stats
    tweet_count = await db.scalar(
        select(func.count()).select_from(Tweet).where(Tweet.user_id == user.id)
    ) or 0
    last_run_result = await db.execute(
        select(ScrapeRun)
        .where(ScrapeRun.user_id == user.id)
        .order_by(ScrapeRun.started_at.desc())
        .limit(1)
    )
    last_run = last_run_result.scalar_one_or_none()

    return request.app.state.templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "subscription": subscription,
            "latest_briefing": latest_briefing,
            "tweet_count": tweet_count,
            "last_run": last_run,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = await get_or_create_settings(db, user.id)
    return request.app.state.templates.TemplateResponse(
        "dashboard/settings.html",
        {"request": request, "user": user, "settings": settings},
    )


@router.get("/briefings", response_class=HTMLResponse)
async def briefings_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
):
    offset = (page - 1) * BRIEFINGS_PER_PAGE

    total = await db.scalar(
        select(func.count()).select_from(Briefing).where(Briefing.user_id == user.id)
    ) or 0

    result = await db.execute(
        select(Briefing)
        .where(Briefing.user_id == user.id)
        .order_by(Briefing.created_at.desc())
        .offset(offset)
        .limit(BRIEFINGS_PER_PAGE)
    )
    briefings = result.scalars().all()
    total_pages = (total + BRIEFINGS_PER_PAGE - 1) // BRIEFINGS_PER_PAGE

    return request.app.state.templates.TemplateResponse(
        "dashboard/briefings.html",
        {
            "request": request,
            "user": user,
            "briefings": briefings,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.get("/briefings/{briefing_id}", response_class=HTMLResponse)
async def briefing_detail(
    briefing_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Briefing).where(Briefing.id == briefing_id, Briefing.user_id == user.id)
    )
    briefing = result.scalar_one_or_none()
    if not briefing:
        return request.app.state.templates.TemplateResponse(
            "dashboard/index.html",
            {"request": request, "user": user, "error": "Briefing not found"},
            status_code=404,
        )

    import markdown
    import nh3

    raw_html = markdown.markdown(briefing.content, extensions=["tables", "fenced_code"])
    html_content = nh3.clean(raw_html, tags=ALLOWED_HTML_TAGS)

    return request.app.state.templates.TemplateResponse(
        "dashboard/briefing_detail.html",
        {
            "request": request,
            "user": user,
            "briefing": briefing,
            "html_content": html_content,
        },
    )


@router.get("/billing", response_class=HTMLResponse)
async def billing_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    success: bool = Query(False),
):
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscription = sub_result.scalar_one_or_none()

    # If returning from Stripe checkout with no local subscription,
    # sync from Stripe (webhooks may not reach localhost)
    if success and not subscription and user.stripe_customer_id:
        subscription = await _sync_subscription_from_stripe(user, db)

    return request.app.state.templates.TemplateResponse(
        "dashboard/billing.html",
        {
            "request": request,
            "user": user,
            "subscription": subscription,
            "stripe_publishable_key": request.app.state.settings.stripe_publishable_key,
        },
    )


async def _sync_subscription_from_stripe(user: User, db: AsyncSession) -> Subscription | None:
    """Fallback: fetch active subscription from Stripe API and create local record."""
    import asyncio
    import stripe
    from web.services.subscription_service import _subscription_from_stripe_data

    try:
        subs = await asyncio.to_thread(
            stripe.Subscription.list,
            customer=user.stripe_customer_id, status="active", limit=1,
        )
        if not subs.data:
            subs = await asyncio.to_thread(
                stripe.Subscription.list,
                customer=user.stripe_customer_id, limit=1,
            )
        if not subs.data:
            return None

        stripe_sub = subs.data[0]
        subscription = _subscription_from_stripe_data(stripe_sub, user.id)
        db.add(subscription)
        await db.commit()
        await db.refresh(subscription)
        logger.info("Synced subscription %s for user %s from Stripe", stripe_sub.id, user.id)
        return subscription
    except Exception as e:
        logger.error("Failed to sync subscription from Stripe: %s", e)
        return None
