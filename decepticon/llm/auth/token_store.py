"""OAuth token storage — secure file-based token persistence.

Token format is compatible with Claude Code CLI's token storage
at ~/.config/anthropic/q/tokens.json.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from decepticon.core.logging import get_logger

log = get_logger("llm.auth.token_store")

# 5-minute buffer for token refresh
REFRESH_BUFFER_SECONDS = 5 * 60


@dataclass
class OAuthTokens:
    """OAuth token set with expiry tracking."""

    access_token: str
    refresh_token: str
    expires_at: int  # Unix timestamp
    scopes: list[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if token is expired or will expire within the buffer period."""
        return time.time() + REFRESH_BUFFER_SECONDS >= self.expires_at

    def time_until_expiry(self) -> float:
        """Seconds until token expires (negative if already expired)."""
        return self.expires_at - time.time()


class TokenStore:
    """Secure file-based OAuth token storage."""

    def load(self, path: Path) -> OAuthTokens | None:
        """Load tokens from a JSON file. Returns None if not found."""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return OAuthTokens(
                access_token=data["accessToken"],
                refresh_token=data["refreshToken"],
                expires_at=data["expiresAt"],
                scopes=data.get("scopes", []),
            )
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Failed to load tokens from %s: %s", path, e)
            return None

    def save(self, path: Path, tokens: OAuthTokens) -> None:
        """Save tokens to a JSON file with restrictive permissions (0o600)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "accessToken": tokens.access_token,
            "refreshToken": tokens.refresh_token,
            "expiresAt": tokens.expires_at,
            "scopes": tokens.scopes,
            "updatedAt": int(time.time() * 1000),
        }
        path.write_text(json.dumps(data, indent=2))
        os.chmod(path, 0o600)
        log.info("Saved OAuth tokens to %s", path)
