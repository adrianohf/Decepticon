"""Base OAuth provider — abstract interface for subscription-based LLM auth.

All OAuth providers (Claude Code, Codex) implement this interface.
The clean separation allows usage from both LiteLLM custom handlers
and potential future direct BaseChatModel subclasses.
"""
from __future__ import annotations

import abc
from pathlib import Path

from decepticon.llm.auth.token_store import OAuthTokens, TokenStore


class BaseOAuthProvider(abc.ABC):
    """Abstract base for OAuth-based LLM providers."""

    def __init__(self) -> None:
        self._store = TokenStore()
        self._cached_tokens: OAuthTokens | None = None

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name (e.g., 'Claude Code')."""

    @property
    @abc.abstractmethod
    def token_path(self) -> Path:
        """Path to the token storage file."""

    @property
    @abc.abstractmethod
    def client_id(self) -> str:
        """OAuth client ID."""

    @property
    @abc.abstractmethod
    def authorize_url(self) -> str:
        """OAuth authorization endpoint."""

    @property
    @abc.abstractmethod
    def token_url(self) -> str:
        """OAuth token exchange endpoint."""

    @abc.abstractmethod
    def get_headers(self, access_token: str) -> dict[str, str]:
        """Build provider-specific request headers."""

    @abc.abstractmethod
    async def start_oauth_flow(self) -> OAuthTokens:
        """Start interactive OAuth login flow (opens browser)."""

    async def get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        tokens = self._cached_tokens or self._store.load(self.token_path)
        if tokens is None:
            raise RuntimeError(
                f"No {self.provider_name} OAuth tokens found at {self.token_path}. "
                f"Run 'decepticon onboard' to authenticate."
            )
        if tokens.is_expired():
            if not tokens.refresh_token:
                raise RuntimeError(
                    f"{self.provider_name} token expired and no refresh token available. "
                    f"Run 'decepticon onboard' to re-authenticate."
                )
            tokens = await self.refresh_token(tokens)
            self._store.save(self.token_path, tokens)
        self._cached_tokens = tokens
        return tokens.access_token

    async def refresh_token(self, tokens: OAuthTokens) -> OAuthTokens:
        """Refresh an expired access token using the refresh token."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": tokens.refresh_token,
                    "client_id": self.client_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        import time
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", tokens.refresh_token),
            expires_at=int(time.time()) + data.get("expires_in", 3600),
            scopes=data.get("scope", "").split(),
        )

    def is_authenticated(self) -> bool:
        """Check if valid tokens exist (may be expired but refreshable)."""
        tokens = self._store.load(self.token_path)
        return tokens is not None

    def clear_tokens(self) -> None:
        """Remove stored tokens (logout)."""
        if self.token_path.exists():
            self.token_path.unlink()
        self._cached_tokens = None
