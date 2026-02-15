"""Auth routes — X OAuth 2.0 PKCE login, callback, logout."""

import json
import logging
import time
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.config import get_settings
from web.constants import DEFAULT_TOKEN_EXPIRY, OAUTH_STATE_TTL
from web.db.encryption import encrypt
from web.db.session import get_db
from web.models.user import User
from web.models.user_settings import UserSettings
from web.services.auth_service import (
    clear_session_cookie,
    create_jwt,
    set_session_cookie,
)
from web.services.twitter_oauth import (
    build_authorize_url,
    exchange_code,
    generate_pkce_pair,
    generate_state,
    get_user_profile,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory fallback for OAuth state (used when Redis is not available)
_oauth_states: dict[str, dict] = {}


async def _get_redis() -> AsyncRedis | None:
    """Get async Redis client if REDIS_URL is configured."""
    settings = get_settings()
    if not settings.redis_url:
        return None
    try:
        return AsyncRedis.from_url(settings.redis_url)
    except Exception:
        return None


async def _store_oauth_state(state: str, data: dict) -> None:
    """Store OAuth state in Redis (or fallback to in-memory)."""
    redis = await _get_redis()
    if redis:
        try:
            await redis.setex(f"oauth:{state}", OAUTH_STATE_TTL, json.dumps(data))
        finally:
            await redis.aclose()
    else:
        _oauth_states[state] = {**data, "created_at": time.monotonic()}


async def _pop_oauth_state(state: str) -> dict | None:
    """Retrieve and delete OAuth state."""
    redis = await _get_redis()
    if redis:
        try:
            raw = await redis.getdel(f"oauth:{state}")
            return json.loads(raw) if raw else None
        finally:
            await redis.aclose()
    else:
        return _oauth_states.pop(state, None)


def _cleanup_expired_states() -> None:
    """Remove expired in-memory OAuth state entries to prevent memory leaks."""
    now = time.monotonic()
    expired = [k for k, v in _oauth_states.items() if now - v.get("created_at", 0) > OAUTH_STATE_TTL]
    for k in expired:
        del _oauth_states[k]


@router.get("/login")
async def login(request: Request):
    """Redirect user to Twitter authorization page."""
    _cleanup_expired_states()

    state = generate_state()
    verifier, challenge = generate_pkce_pair()
    await _store_oauth_state(state, {"code_verifier": verifier})

    url = build_authorize_url(state, challenge)
    logger.debug("OAuth authorize URL: %s", url)
    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Twitter OAuth callback — exchange code, create/update user."""
    # Validate state
    stored = await _pop_oauth_state(state)
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    # Check TTL (only relevant for in-memory fallback; Redis uses setex auto-expiry)
    if stored.get("created_at") and time.monotonic() - stored["created_at"] > OAUTH_STATE_TTL:
        raise HTTPException(status_code=400, detail="OAuth state expired. Please try logging in again.")

    try:
        # Exchange code for tokens
        token_data = await exchange_code(code, stored["code_verifier"])
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", DEFAULT_TOKEN_EXPIRY)

        # Fetch user profile
        profile = await get_user_profile(access_token)
        x_user_id = profile["id"]
        x_username = profile["username"]
        x_display_name = profile.get("name")

    except Exception as e:
        logger.error("OAuth callback error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Authentication failed. Please try logging in again.",
        )

    # Create or update user
    result = await db.execute(select(User).where(User.x_user_id == x_user_id))
    user = result.scalar_one_or_none()

    if user:
        user.x_username = x_username
        user.x_display_name = x_display_name
        user.x_access_token = encrypt(access_token)
        user.x_refresh_token = encrypt(refresh_token) if refresh_token else None
        user.x_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    else:
        user = User(
            x_user_id=x_user_id,
            x_username=x_username,
            x_display_name=x_display_name,
            x_access_token=encrypt(access_token),
            x_refresh_token=encrypt(refresh_token) if refresh_token else None,
            x_token_expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        )
        db.add(user)
        await db.flush()

        # Create default settings
        settings = UserSettings(user_id=user.id)
        db.add(settings)

    await db.commit()
    await db.refresh(user)

    # Set session cookie and redirect to dashboard
    token = create_jwt(user.id)
    response = RedirectResponse(url="/app/dashboard", status_code=303)
    set_session_cookie(response, token)
    return response


@router.get("/admin-login")
async def admin_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Debug-only: log in as the seeded admin user (no OAuth required).

    Only works when DEBUG=true AND request comes from localhost.
    """
    settings = get_settings()
    if not settings.debug:
        raise HTTPException(status_code=404)

    # Only allow from localhost
    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=404)

    result = await db.execute(select(User).where(User.x_user_id == "admin_local"))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Admin user not found. Run: python -m web.admin_seed",
        )

    token = create_jwt(user.id)
    response = RedirectResponse(url="/app/dashboard", status_code=303)
    set_session_cookie(response, token)
    return response


@router.post("/logout")
async def logout():
    """Clear session cookie and redirect to landing."""
    response = RedirectResponse(url="/", status_code=303)
    clear_session_cookie(response)
    return response
