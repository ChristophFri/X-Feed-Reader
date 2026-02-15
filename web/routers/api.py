"""API routes — HTMX partials and JSON endpoints."""

import json
from html import escape as html_escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from web.db.session import get_db
from web.models.user import User
from web.schemas.settings import SettingsUpdate
from web.services.auth_service import get_current_user
from web.services.delivery_service import deliver_briefing
from web.services.pipeline_service import run_user_pipeline
from web.services.subscription_service import create_checkout_session, create_portal_session
from web.services.user_service import update_settings

router = APIRouter(prefix="/api", tags=["api"])


def _toast_response(html: str, message: str, toast_type: str = "success") -> Response:
    """Return an HTML response with an HX-Trigger header for toast notifications."""
    trigger = json.dumps({"showToast": {"message": message, "type": toast_type}})
    return Response(content=html, media_type="text/html", headers={"HX-Trigger": trigger})


@router.post("/settings/prompt", response_class=HTMLResponse)
async def update_prompt_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    updates = SettingsUpdate(
        prompt_preset=form.get("prompt_preset"),
        custom_prompt=form.get("custom_prompt") or None,
    )
    settings = await update_settings(db, user.id, updates)

    html = request.app.state.templates.get_template("partials/settings_form.html").render(
        request=request, settings=settings, section="prompt"
    )
    return _toast_response(html, "Prompt settings saved")


@router.post("/settings/schedule", response_class=HTMLResponse)
async def update_schedule_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    updates = SettingsUpdate(
        schedule_hour=int(form.get("schedule_hour", 8)),
        timezone=form.get("timezone", "UTC"),
    )
    settings = await update_settings(db, user.id, updates)

    html = request.app.state.templates.get_template("partials/settings_form.html").render(
        request=request, settings=settings, section="schedule"
    )
    return _toast_response(html, "Schedule settings saved")


@router.post("/settings/delivery", response_class=HTMLResponse)
async def update_delivery_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    updates = SettingsUpdate(
        delivery_email=form.get("delivery_email") == "on",
        delivery_telegram=form.get("delivery_telegram") == "on",
        telegram_bot_token=form.get("telegram_bot_token") or None,
        telegram_chat_id=form.get("telegram_chat_id") or None,
    )
    settings = await update_settings(db, user.id, updates)

    html = request.app.state.templates.get_template("partials/settings_form.html").render(
        request=request, settings=settings, section="delivery"
    )
    return _toast_response(html, "Delivery settings saved")


@router.post("/settings/advanced", response_class=HTMLResponse)
async def update_advanced_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    updates = SettingsUpdate(
        feed_source=form.get("feed_source", "api"),
        max_tweets=int(form.get("max_tweets", 100)),
        summary_hours=int(form.get("summary_hours", 24)),
        llm_provider=form.get("llm_provider", "openai"),
        llm_model=form.get("llm_model") or None,
    )
    settings = await update_settings(db, user.id, updates)

    html = request.app.state.templates.get_template("partials/settings_form.html").render(
        request=request, settings=settings, section="advanced"
    )
    return _toast_response(html, "Advanced settings saved")


# --- Billing endpoints ---


@router.post("/billing/checkout")
async def billing_checkout(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    url = await create_checkout_session(user, db)
    return RedirectResponse(url, status_code=303)


@router.post("/billing/portal")
async def billing_portal(
    user: User = Depends(get_current_user),
):
    url = await create_portal_session(user)
    return RedirectResponse(url, status_code=303)


# --- Pipeline endpoints ---


@router.post("/pipeline/run", response_class=HTMLResponse)
async def run_pipeline(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the full pipeline for the current user (manual trigger)."""
    try:
        briefing = await run_user_pipeline(user.id, db)
    except Exception as e:
        error_msg = html_escape(str(e))
        error_html = (
            f'<div class="p-4 rounded-lg bg-red-900/30 border border-red-700/40 text-red-300 text-sm">'
            f'Pipeline error: {error_msg}'
            f'</div>'
        )
        return _toast_response(error_html, "Pipeline failed", "error")

    if briefing:
        # Also deliver immediately
        await deliver_briefing(briefing, db)
        html = (
            f'<div class="p-4 rounded-lg bg-green-900/30 border border-green-700/40 text-green-300 text-sm">'
            f'Briefing generated! {briefing.tweet_count} tweets summarized. '
            f'<a href="/app/briefings/{briefing.id}" class="underline text-green-200">View briefing &rarr;</a>'
            f'</div>'
        )
        return _toast_response(html, "Pipeline completed successfully")
    else:
        html = (
            '<div class="p-4 rounded-lg bg-amber-900/30 border border-amber-700/40 text-amber-300 text-sm">'
            'No briefing generated. Check that your X account is connected and tweets are available.'
            '</div>'
        )
        return _toast_response(html, "No briefing generated", "info")
