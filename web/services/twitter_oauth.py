"""Twitter/X OAuth 2.0 PKCE flow helpers."""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

from web.config import get_settings
from web.constants import TWITTER_AUTHORIZE_URL, TWITTER_TOKEN_URL, TWITTER_USER_ME_URL, TWITTER_SCOPES
from web.http_client import get_http_client


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorize_url(state: str, code_challenge: str) -> str:
    """Build the Twitter authorization URL for PKCE."""
    settings = get_settings()
    params = {
        "response_type": "code",
        "client_id": settings.twitter_client_id,
        "redirect_uri": settings.twitter_redirect_uri,
        "scope": TWITTER_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{TWITTER_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str, code_verifier: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    settings = get_settings()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.twitter_redirect_uri,
        "code_verifier": code_verifier,
        "client_id": settings.twitter_client_id,
    }
    client = get_http_client()
    resp = await client.post(
        TWITTER_TOKEN_URL,
        data=data,
        auth=(settings.twitter_client_id, settings.twitter_client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Use refresh token to get a new access token."""
    settings = get_settings()
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.twitter_client_id,
    }
    client = get_http_client()
    resp = await client.post(
        TWITTER_TOKEN_URL,
        data=data,
        auth=(settings.twitter_client_id, settings.twitter_client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()


async def get_user_profile(access_token: str) -> dict:
    """Fetch the authenticated user's profile from Twitter API v2."""
    client = get_http_client()
    resp = await client.get(
        TWITTER_USER_ME_URL,
        params={"user.fields": "id,name,username,profile_image_url"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    resp.raise_for_status()
    return resp.json()["data"]
