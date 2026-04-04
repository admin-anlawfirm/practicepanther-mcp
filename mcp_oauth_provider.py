"""
MCP OAuth 2.0 Authorization Server Provider.

Implements the OAuthAuthorizationServerProvider protocol from the MCP SDK,
proxying authorization through PracticePanther's OAuth flow.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import time
from uuid import uuid4

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from oauth import get_authorize_url
from pp_client import _encrypt, _decrypt, _get_redis

logger = logging.getLogger("pp-mcp")

# Allowed redirect URI patterns for OAuth clients.
# - claude.ai callback: for Claude.ai web connector
# - localhost/127.0.0.1: for mcp-remote (Claude Code) OAuth flow
ALLOWED_REDIRECT_PATTERNS = [
    re.compile(r"^https://claude\.ai/api/mcp/auth_callback$"),
    re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?/.*$"),
]


def _is_redirect_uri_allowed(uri: str) -> bool:
    """Check if a redirect URI matches an allowed pattern."""
    return any(p.match(uri) for p in ALLOWED_REDIRECT_PATTERNS)


# ---------------------------------------------------------------------------
# Dual-backend key-value store (Redis with in-memory fallback)
# ---------------------------------------------------------------------------

class OAuthStore:
    """Simple key-value store with TTL support. Uses Redis if available,
    otherwise falls back to an in-memory dict."""

    def __init__(self) -> None:
        self._mem: dict[str, tuple[str, float]] = {}  # key -> (value, expires_at)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        encrypted = _encrypt(value)
        r = _get_redis()
        if r:
            r.setex(key, ttl_seconds, encrypted)
        else:
            self._mem[key] = (encrypted, time.time() + ttl_seconds)

    def get(self, key: str) -> str | None:
        r = _get_redis()
        if r:
            data = r.get(key)
            return _decrypt(data) if data else None
        entry = self._mem.get(key)
        if entry is None:
            return None
        encrypted, expires_at = entry
        if time.time() >= expires_at:
            del self._mem[key]
            return None
        return _decrypt(encrypted)

    def delete(self, key: str) -> None:
        r = _get_redis()
        if r:
            r.delete(key)
        else:
            self._mem.pop(key, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# TTLs
CLIENT_TTL = 90 * 86400       # 90 days
AUTH_FLOW_TTL = 600            # 10 minutes
AUTH_CODE_TTL = 300            # 5 minutes
ACCESS_TOKEN_TTL = 3600        # 1 hour
REFRESH_TOKEN_TTL = 30 * 86400 # 30 days


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class PracticePantherOAuthProvider(OAuthAuthorizationServerProvider):
    """MCP OAuth provider that proxies auth through PracticePanther OAuth."""

    def __init__(self, store: OAuthStore, issuer_url: str) -> None:
        self.store = store
        self.issuer_url = issuer_url

    # -- Client registration --------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        data = self.store.get(f"mcp:client:{client_id}")
        if data is None:
            return None  # Reject unregistered clients
        return OAuthClientInformationFull.model_validate_json(data)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Validate all redirect URIs against allowlist
        for uri in client_info.redirect_uris:
            if not _is_redirect_uri_allowed(str(uri)):
                logger.warning("Client registration rejected: invalid redirect_uri %s", uri)
                raise ValueError(f"Redirect URI not allowed: {uri}")
        logger.info("Client registered: %s", client_info.client_id)
        self.store.set(
            f"mcp:client:{client_info.client_id}",
            client_info.model_dump_json(),
            CLIENT_TTL,
        )

    # -- Authorization --------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Store the pending auth flow and redirect to PracticePanther OAuth."""
        flow_id = uuid4().hex

        flow_data = json.dumps({
            "client_id": client.client_id,
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "state": params.state,
            "scopes": params.scopes or [],
            "resource": params.resource,
        })
        self.store.set(f"mcp:authflow:{flow_id}", flow_data, AUTH_FLOW_TTL)

        # Redirect to PracticePanther OAuth, using flow_id as the PP state
        # so we can link back when PP redirects to /oauth/callback
        pp_auth_url = get_authorize_url(state=flow_id)
        return pp_auth_url

    # -- Authorization code ---------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code_hash = _hash_token(authorization_code)
        data = self.store.get(f"mcp:authcode:{code_hash}")
        if data is None:
            return None
        record = json.loads(data)
        if time.time() >= record["expires_at"]:
            self.store.delete(f"mcp:authcode:{code_hash}")
            return None
        return AuthorizationCode(
            code=authorization_code,
            client_id=record["client_id"],
            code_challenge=record["code_challenge"],
            redirect_uri=record["redirect_uri"],
            redirect_uri_provided_explicitly=record["redirect_uri_provided_explicitly"],
            scopes=record.get("scopes") or [],
            expires_at=record["expires_at"],
            resource=record.get("resource"),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # Delete the auth code (single-use)
        code_hash = _hash_token(authorization_code.code)
        self.store.delete(f"mcp:authcode:{code_hash}")

        # Issue new access + refresh tokens
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        expires_at = time.time() + ACCESS_TOKEN_TTL

        self.store.set(
            f"mcp:access:{_hash_token(access_token)}",
            json.dumps({
                "client_id": client.client_id,
                "scopes": authorization_code.scopes,
                "expires_at": expires_at,
                "resource": authorization_code.resource,
            }),
            ACCESS_TOKEN_TTL,
        )
        self.store.set(
            f"mcp:refresh:{_hash_token(refresh_token)}",
            json.dumps({
                "client_id": client.client_id,
                "scopes": authorization_code.scopes,
            }),
            REFRESH_TOKEN_TTL,
        )

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_token,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    # -- Access token ---------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        token_hash = _hash_token(token)
        data = self.store.get(f"mcp:access:{token_hash}")
        if data is None:
            return None
        record = json.loads(data)
        if time.time() >= record["expires_at"]:
            self.store.delete(f"mcp:access:{token_hash}")
            return None
        return AccessToken(
            token=token,
            client_id=record["client_id"],
            scopes=record["scopes"],
            expires_at=int(record["expires_at"]),
            resource=record.get("resource"),
        )

    # -- Refresh token --------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        token_hash = _hash_token(refresh_token)
        data = self.store.get(f"mcp:refresh:{token_hash}")
        if data is None:
            return None
        record = json.loads(data)
        return RefreshToken(
            token=refresh_token,
            client_id=record["client_id"],
            scopes=record["scopes"],
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Revoke old refresh token
        old_hash = _hash_token(refresh_token.token)
        self.store.delete(f"mcp:refresh:{old_hash}")

        # Issue new tokens
        new_access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        use_scopes = scopes if scopes else refresh_token.scopes
        expires_at = time.time() + ACCESS_TOKEN_TTL

        self.store.set(
            f"mcp:access:{_hash_token(new_access)}",
            json.dumps({
                "client_id": client.client_id,
                "scopes": use_scopes,
                "expires_at": expires_at,
            }),
            ACCESS_TOKEN_TTL,
        )
        self.store.set(
            f"mcp:refresh:{_hash_token(new_refresh)}",
            json.dumps({
                "client_id": client.client_id,
                "scopes": use_scopes,
            }),
            REFRESH_TOKEN_TTL,
        )

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=new_refresh,
            scope=" ".join(use_scopes) if use_scopes else None,
        )

    # -- Revocation -----------------------------------------------------------

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        token_hash = _hash_token(token.token)
        if isinstance(token, AccessToken):
            self.store.delete(f"mcp:access:{token_hash}")
        else:
            self.store.delete(f"mcp:refresh:{token_hash}")
