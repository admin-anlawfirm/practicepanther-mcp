"""PracticePanther API client with OAuth token management."""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("pp-mcp")

BASE_URL = "https://app.practicepanther.com"
API_V2 = f"{BASE_URL}/api/v2"

# ---------------------------------------------------------------------------
# Encryption helpers (Fernet AES-128-CBC + HMAC)
# ---------------------------------------------------------------------------

_fernet = None


def _get_fernet():
    """Return a Fernet cipher if TOKEN_ENCRYPTION_KEY is set, else None."""
    global _fernet
    if _fernet is None:
        key = os.environ.get("TOKEN_ENCRYPTION_KEY", "").strip()
        if key:
            from cryptography.fernet import Fernet
            _fernet = Fernet(key.encode())
        else:
            _fernet = False  # Sentinel: checked, not available
    return _fernet if _fernet is not False else None


def _encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns plaintext unchanged if no key configured."""
    f = _get_fernet()
    if f:
        return f.encrypt(plaintext.encode()).decode()
    return plaintext


def _decrypt(ciphertext: str) -> str:
    """Decrypt a string. Returns input unchanged if no key configured.
    Gracefully handles legacy unencrypted data (returns as-is)."""
    f = _get_fernet()
    if f:
        try:
            return f.decrypt(ciphertext.encode()).decode()
        except Exception:
            # Legacy data stored before encryption was enabled
            return ciphertext
    return ciphertext


# ---------------------------------------------------------------------------
# Redis-backed token persistence
# ---------------------------------------------------------------------------

_redis_client = None
_redis_warned = False
REDIS_KEY = "pp_oauth_tokens"


def _get_redis():
    global _redis_client, _redis_warned
    if _redis_client is None:
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                import redis
                _redis_client = redis.from_url(redis_url, decode_responses=True)
                _redis_client.ping()
            except Exception as e:
                logger.warning("Redis unavailable, using in-memory token storage (tokens lost on restart): %s", e)
                _redis_client = False  # Sentinel: don't retry
                _redis_warned = True
        elif not _redis_warned:
            logger.info("REDIS_URL not set, using in-memory token storage")
            _redis_warned = True
    return _redis_client if _redis_client is not False else None


def _save_tokens_to_redis(access_token: str, refresh_token: str, expires_at: float) -> None:
    r = _get_redis()
    if r:
        r.set(REDIS_KEY, _encrypt(json.dumps({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
        })))


def _load_tokens_from_redis() -> dict | None:
    r = _get_redis()
    if r:
        data = r.get(REDIS_KEY)
        if data:
            return json.loads(_decrypt(data))
    return None


# ---------------------------------------------------------------------------
# Token store
# ---------------------------------------------------------------------------

class TokenStore:
    """OAuth token storage with Redis persistence."""

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.expires_at: float = 0
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True
            saved = _load_tokens_from_redis()
            if saved:
                self.access_token = saved["access_token"]
                self.refresh_token = saved["refresh_token"]
                self.expires_at = saved["expires_at"]

    def set_tokens(self, access_token: str, refresh_token: str, expires_in: int) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = time.time() + expires_in - 60  # 60s buffer
        _save_tokens_to_redis(access_token, refresh_token, self.expires_at)

    @property
    def is_expired(self) -> bool:
        self._ensure_loaded()
        return time.time() >= self.expires_at

    @property
    def is_authenticated(self) -> bool:
        self._ensure_loaded()
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
            logger.error("PP API %s /%s returned %s: %s", method, path, resp.status_code, error_body)
            raise RuntimeError(
                f"PP API {method} /{path} returned {resp.status_code}"
            )

        if is_download:
            return {"content": resp.content.hex(), "content_type": resp.headers.get("content-type")}

        if resp.status_code == 204 or not resp.content:
            return {"status": "success"}

        return resp.json()


# ---------------------------------------------------------------------------
# OData query helpers
# ---------------------------------------------------------------------------


def build_odata_params(
    *,
    top: int | None = None,
    skip: int | None = None,
    odata_filter: str | None = None,
    orderby: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a params dict merging regular filters with OData query options.

    OData params supported by PracticePanther API v2:
      $top     - max records to return (pagination)
      $skip    - records to skip (pagination)
      $filter  - OData filter expression, e.g. "contains(user/name, 'john')"
      $orderby - sort expression, e.g. "date desc"
    """
    params: dict[str, Any] = {}
    # Regular filter params (None values stripped)
    for k, v in extra.items():
        if v is not None:
            params[k] = v
    # OData system query options
    if top is not None:
        params["$top"] = top
    if skip is not None:
        params["$skip"] = skip
    if odata_filter is not None:
        params["$filter"] = odata_filter
    if orderby is not None:
        params["$orderby"] = orderby
    return params


# Convenience wrappers
async def api_get(path: str, **params: Any) -> Any:
    return await api_request("GET", path, params=params if params else None)


async def api_post(path: str, body: dict[str, Any]) -> Any:
    return await api_request("POST", path, json_body=body)


async def api_put(path: str, id: str, body: dict[str, Any]) -> Any:
    return await api_request("PUT", path, params={"id": id}, json_body=body)


async def api_delete(path: str, id: str) -> Any:
    return await api_request("DELETE", path, params={"id": id})
