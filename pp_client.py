"""PracticePanther API client with OAuth token management."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

BASE_URL = "https://app.practicepanther.com"
API_V2 = f"{BASE_URL}/api/v2"


class TokenStore:
    """In-memory OAuth token storage with expiry tracking."""

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.expires_at: float = 0

    def set_tokens(self, access_token: str, refresh_token: str, expires_in: int) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = time.time() + expires_in - 60  # 60s buffer

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    @property
    def is_authenticated(self) -> bool:
        return self.access_token is not None


token_store = TokenStore()


async def refresh_access_token() -> None:
    """Refresh the access token using the stored refresh token."""
    if not token_store.refresh_token:
        raise RuntimeError("No refresh token available. Please re-authorize via get_auth_url.")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_store.refresh_token,
                "client_id": os.environ["PP_CLIENT_ID"],
                "client_secret": os.environ["PP_CLIENT_SECRET"],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token_store.set_tokens(
            data["access_token"],
            data.get("refresh_token", token_store.refresh_token),
            data.get("expires_in", 86400),
        )


async def _ensure_auth() -> str:
    """Return a valid access token, refreshing if needed."""
    if not token_store.is_authenticated:
        raise RuntimeError(
            "Not authenticated. Call get_auth_url first, then visit the URL to authorize."
        )
    if token_store.is_expired:
        await refresh_access_token()
    return token_store.access_token  # type: ignore[return-value]


async def api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    data: Any = None,
    files: Any = None,
    is_download: bool = False,
) -> Any:
    """Make an authenticated request to the PracticePanther API."""
    access_token = await _ensure_auth()

    # Clean None values from params
    if params:
        params = {k: v for k, v in params.items() if v is not None}

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.request(
            method,
            f"{API_V2}/{path}" if not path.startswith("http") else path,
            params=params,
            json=json_body,
            data=data,
            files=files,
            headers=headers,
        )
        if resp.status_code >= 400:
            try:
                error_body = resp.text
            except Exception:
                error_body = ""
            raise RuntimeError(
                f"PP API {method} /{path} returned {resp.status_code}: {error_body}"
            )

        if is_download:
            return {"content": resp.content.hex(), "content_type": resp.headers.get("content-type")}

        if resp.status_code == 204 or not resp.content:
            return {"status": "success"}

        return resp.json()


# Convenience wrappers
async def api_get(path: str, **params: Any) -> Any:
    return await api_request("GET", path, params=params if params else None)


async def api_post(path: str, body: dict[str, Any]) -> Any:
    return await api_request("POST", path, json_body=body)


async def api_put(path: str, id: str, body: dict[str, Any]) -> Any:
    return await api_request("PUT", path, params={"id": id}, json_body=body)


async def api_delete(path: str, id: str) -> Any:
    return await api_request("DELETE", path, params={"id": id})
