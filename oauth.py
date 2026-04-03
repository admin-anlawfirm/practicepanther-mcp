"""OAuth 2.0 helpers for PracticePanther."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx

from pp_client import BASE_URL, token_store

AUTHORIZE_URL = f"{BASE_URL}/oauth/authorize"
TOKEN_URL = f"{BASE_URL}/oauth/token"


def get_authorize_url(state: str = "mcp") -> str:
    """Build the OAuth authorization URL for the user to visit."""
    params = {
        "response_type": "code",
        "client_id": os.environ["PP_CLIENT_ID"],
        "redirect_uri": os.environ["PP_REDIRECT_URI"],
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange an authorization code for access and refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": os.environ["PP_CLIENT_ID"],
                "client_secret": os.environ["PP_CLIENT_SECRET"],
                "redirect_uri": os.environ["PP_REDIRECT_URI"],
            },
        )
        resp.raise_for_status()
        data = resp.json()

        token_store.set_tokens(
            data["access_token"],
            data["refresh_token"],
            data.get("expires_in", 86400),
        )

        return {"status": "authenticated", "expires_in": data.get("expires_in", 86400)}
