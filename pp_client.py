"""PracticePanther API client with OAuth token management."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Any, Callable

import httpx

logger = logging.getLogger("pp-mcp")

BASE_URL = "https://app.practicepanther.com"
API_V2 = f"{BASE_URL}/api/v2"


class PPAuthExpired(RuntimeError):
    """PracticePanther refused our credentials and they cannot be refreshed.
    The user must re-authorize via the OAuth flow."""


# Hook invoked when PP auth permanently fails. Set by server.py at startup
# so that MCP-layer tokens can be invalidated alongside PP-layer tokens,
# forcing Claude to start a fresh OAuth flow.
on_pp_auth_expired: Callable[[], None] | None = None

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

    Gracefully handles legacy unencrypted data: if the input does NOT look
    like a Fernet token (which always starts with 'gAAAAA' base64-encoded),
    we treat it as plaintext from before encryption was enabled.

    If the input DOES look like Fernet but decryption fails, that means key
    rotation or corruption — raise loudly. Silently returning ciphertext as
    "plaintext" causes downstream API errors hours later that look like auth
    bugs but are really key/data drift."""
    f = _get_fernet()
    if not f:
        return ciphertext
    if not ciphertext.startswith("gAAAAA"):
        # Legacy unencrypted data stored before encryption was enabled
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.error(
            "Token decryption failed — TOKEN_ENCRYPTION_KEY may have rotated "
            "or stored data is corrupted. Re-authorize via the OAuth flow."
        )
        raise RuntimeError("Token decryption failed") from e


# ---------------------------------------------------------------------------
# Redis-backed token persistence
# ---------------------------------------------------------------------------

_redis_client = None
_redis_warned = False
REDIS_KEY = "pp_oauth_tokens"


def _get_redis():
    """Return a Redis client if REDIS_URL is set and reachable.

    Behavior:
    - REDIS_URL set + reachable → use Redis.
    - REDIS_URL set + unreachable → raise. Falling back to in-memory in
      production silently loses tokens on the next restart and produces the
      "auth error after idle" disconnect symptom. Set ALLOW_INMEMORY_TOKENS=1
      to opt in to the legacy fallback for dev/test.
    - REDIS_URL unset → in-memory (local dev default).
    """
    global _redis_client, _redis_warned
    if _redis_client is None:
        redis_url = os.environ.get("REDIS_URL")
        allow_fallback = os.environ.get("ALLOW_INMEMORY_TOKENS", "").strip().lower() in ("1", "true", "yes")
        if redis_url:
            try:
                import redis
                _redis_client = redis.from_url(redis_url, decode_responses=True)
                _redis_client.ping()
            except Exception as e:
                if allow_fallback:
                    logger.warning("Redis unavailable, falling back to in-memory token storage (ALLOW_INMEMORY_TOKENS set): %s", e)
                    _redis_client = False
                    _redis_warned = True
                else:
                    logger.error("REDIS_URL is set but Redis is unreachable: %s", e)
                    raise RuntimeError(
                        f"Redis unreachable at REDIS_URL: {e}. "
                        "Set ALLOW_INMEMORY_TOKENS=1 to allow in-memory fallback (dev only)."
                    ) from e
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


def _delete_tokens_from_redis() -> None:
    r = _get_redis()
    if r:
        r.delete(REDIS_KEY)


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

    def clear(self) -> None:
        """Wipe tokens from memory and Redis. Used when PP rejects credentials."""
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0
        self._loaded = True  # Don't reload from Redis after clearing
        _delete_tokens_from_redis()


token_store = TokenStore()

# Serializes concurrent refreshes so multiple in-flight tool calls don't all
# POST to /oauth/token simultaneously.
_refresh_lock = asyncio.Lock()


def _is_permanent_auth_failure(status: int, body: str) -> bool:
    """PP returned a status/body that means the refresh token is dead and a
    retry won't help — the user must re-auth."""
    if status == 401:
        return True
    if status == 400 and ("invalid_grant" in body or "invalid_client" in body):
        return True
    return False


def _signal_pp_auth_expired() -> None:
    """Tell the MCP layer to drop its tokens too, so Claude prompts re-auth."""
    token_store.clear()
    cb = on_pp_auth_expired
    if cb:
        try:
            cb()
        except Exception as e:
            logger.error("on_pp_auth_expired callback raised: %s", e)


async def refresh_access_token() -> None:
    """Refresh the access token using the stored refresh token.

    Serialized via _refresh_lock so concurrent callers don't race on the PP
    /oauth/token endpoint. Inside the lock we re-check expiry — if another
    coroutine already refreshed while we were waiting, we return immediately.
    """
    async with _refresh_lock:
        # Another coroutine may have refreshed while we waited for the lock.
        if not token_store.is_expired and token_store.is_authenticated:
            return

        if not token_store.refresh_token:
            raise PPAuthExpired(
                "No refresh token available. Please re-authorize via get_auth_url."
            )

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

        if resp.status_code >= 400:
            body = resp.text
            logger.error("PP /oauth/token (refresh_token) returned %s: %s", resp.status_code, body)
            if _is_permanent_auth_failure(resp.status_code, body):
                _signal_pp_auth_expired()
                raise PPAuthExpired(
                    f"PP refresh token rejected ({resp.status_code}). User must re-authorize."
                )
            raise RuntimeError(f"PP /oauth/token returned {resp.status_code}: {body}")

        data = resp.json()
        token_store.set_tokens(
            data["access_token"],
            data.get("refresh_token", token_store.refresh_token),
            data.get("expires_in", 86400),
        )


async def _ensure_auth() -> str:
    """Return a valid access token, refreshing if needed."""
    if not token_store.is_authenticated:
        raise PPAuthExpired(
            "Not authenticated. Call get_auth_url first, then visit the URL to authorize."
        )
    if token_store.is_expired:
        await refresh_access_token()
        if not token_store.is_authenticated:
            raise PPAuthExpired("PP credentials cleared after failed refresh.")
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
    """Make an authenticated request to the PracticePanther API.

    On 401, force-refresh the access token and retry once. PP can revoke a
    still-unexpired access token server-side (user revokes from PP UI,
    password change, admin de-auth) — without this retry, the next tool
    call after such a revocation fails immediately with no recovery path.
    """
    # Clean None values from params
    if params:
        params = {k: v for k, v in params.items() if v is not None}

    url = f"{API_V2}/{path}" if not path.startswith("http") else path

    async def _do_request() -> httpx.Response:
        access_token = await _ensure_auth()
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=60) as client:
            return await client.request(
                method, url,
                params=params, json=json_body, data=data, files=files,
                headers=headers,
            )

    resp = await _do_request()

    if resp.status_code == 401:
        logger.info("PP API %s /%s got 401, forcing refresh and retrying once", method, path)
        token_store.expires_at = 0  # force refresh on the retry
        try:
            resp = await _do_request()
        except PPAuthExpired:
            raise
        if resp.status_code == 401:
            logger.error("PP API %s /%s still 401 after refresh — credentials revoked", method, path)
            _signal_pp_auth_expired()
            raise PPAuthExpired(
                f"PP API {method} /{path} returned 401 after refresh. User must re-authorize."
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


# Fields the server manages — never echo them back on a merged PUT.
_SERVER_MANAGED_FIELDS = frozenset({"id", "created_at", "updated_at"})


async def api_put_merge(resource: str, id: str, partial: dict[str, Any]) -> Any:
    """PATCH-semantics update for a PP resource that only exposes full-replace PUT.

    Reads the current object, drops server-managed fields, merges the caller's
    partial payload on top, and PUTs the merged object. Fields omitted from
    ``partial`` are preserved from the server's current state, so callers can
    update a single field without wiping the rest (e.g. without orphaning a
    task from its matter by omitting matter_ref).

    ``resource`` is used for both the GET (``{resource}/{id}``) and the PUT
    (``{resource}?id=...``) — PP uses the same path for both in every case we
    call this for.
    """
    existing = await api_request("GET", f"{resource}/{id}")
    if not isinstance(existing, dict):
        raise RuntimeError(
            f"Cannot merge update for {resource}/{id}: GET did not return a single object"
        )
    merged: dict[str, Any] = {
        k: v for k, v in existing.items() if k not in _SERVER_MANAGED_FIELDS
    }
    merged.update(partial)
    return await api_put(resource, id, merged)


async def api_delete(path: str, id: str) -> Any:
    return await api_request("DELETE", path, params={"id": id})
