"""Claude Code OAuth provider — subscription-based Anthropic API access.

Implements OAuth 2.0 + PKCE flow to obtain Anthropic access tokens using
a Claude Code (or Claude Pro/Max) subscription. No API key required.

Reference: not-claude-code-emulator/src/services/oauth-flow.ts
           not-claude-code-emulator/src/config/oauth.ts
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

import httpx

from decepticon.core.logging import get_logger
from decepticon.llm.auth.base import BaseOAuthProvider
from decepticon.llm.auth.headers import build_anthropic_headers
from decepticon.llm.auth.token_store import OAuthTokens

log = get_logger("llm.auth.claude_code")

# OAuth configuration — matches Claude Code CLI defaults
CLAUDE_AI_AUTHORIZE_URL = "https://claude.com/cai/oauth/authorize"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Claude Code stores credentials here (NOT ~/.config/anthropic/q/tokens.json)
CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
# Legacy path for backward compatibility with older Claude Code versions
LEGACY_TOKEN_PATH = Path.home() / ".config" / "anthropic" / "q" / "tokens.json"

OAUTH_SCOPES = [
    "user:profile",
    "user:inference",
    "user:sessions:claude_code",
    "user:mcp_servers",
    "user:file_upload",
]


def _base64url(data: bytes) -> str:
    """Base64url-encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _generate_code_verifier() -> str:
    return _base64url(secrets.token_bytes(32))


def _generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return _base64url(digest)


def _generate_state() -> str:
    return _base64url(secrets.token_bytes(24))


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback authorization code."""

    authorization_code: str | None = None
    received_state: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code:
            _CallbackHandler.authorization_code = code
            _CallbackHandler.received_state = state
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authentication successful!</h1>"
                b"<p>You can close this window and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing authorization code")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress default HTTP server logging."""


OAUTH_TOKEN_PATTERN = "sk-ant-oat01-"


def _is_valid_oauth_token(token: str) -> bool:
    """Validate that a token looks like a Claude OAuth token."""
    return token.startswith(OAUTH_TOKEN_PATTERN)


def _load_claude_code_tokens() -> OAuthTokens | None:
    """Load tokens following the same resolution order as the reference impl.

    Resolution order (matching not-claude-code-emulator):
      1. ``ANTHROPIC_OAUTH_TOKEN`` environment variable
      2. ``~/.claude/.credentials.json`` (Claude Code CLI current format)
      3. ``~/.config/anthropic/q/tokens.json`` (legacy / emulator format)

    Claude Code stores credentials at ``~/.claude/.credentials.json`` with
    tokens nested under the ``claudeAiOauth`` key. ``expiresAt`` is in
    **milliseconds** (JavaScript Date.now() format).
    """
    import json

    # 1. Environment variable (matches emulator's resolveFallbackOAuthToken)
    env_token = os.environ.get("ANTHROPIC_OAUTH_TOKEN", "").strip()
    if env_token and _is_valid_oauth_token(env_token):
        log.info("Using ANTHROPIC_OAUTH_TOKEN from environment")
        return OAuthTokens(
            access_token=env_token,
            refresh_token="",
            expires_at=0,  # No expiry info from env — never auto-refresh
            scopes=["user:inference"],
        )

    # 2+3. File-based token stores
    # TODO: macOS Keychain support ("Claude Code-credentials") — openclaw reads
    #       Keychain first on darwin via `security find-generic-password`.
    for path in (CREDENTIALS_PATH, LEGACY_TOKEN_PATH):
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text())

            # Current format: nested under claudeAiOauth
            # (matches openclaw's parseClaudeCliOauthCredential)
            if "claudeAiOauth" in raw:
                oauth = raw["claudeAiOauth"]
                token = oauth.get("accessToken", "")
                if not _is_valid_oauth_token(token):
                    log.warning("Invalid token format in %s", path)
                    continue
                expires_at = oauth.get("expiresAt", 0)
                # Validate expiresAt (openclaw checks isFinite and > 0)
                if not isinstance(expires_at, (int, float)) or expires_at <= 0:
                    log.warning("Invalid expiresAt in %s", path)
                    continue
                # Convert ms → s for Python (JS Date.now() is ms)
                if expires_at > 1e12:
                    expires_at = int(expires_at / 1000)
                refresh_token = oauth.get("refreshToken", "")
                # openclaw: refreshToken present → "oauth" (refreshable)
                #           refreshToken absent → "token" (non-refreshable)
                return OAuthTokens(
                    access_token=token,
                    refresh_token=refresh_token if isinstance(refresh_token, str) else "",
                    expires_at=expires_at,
                    scopes=oauth.get("scopes", []),
                )

            # Legacy format: top-level keys (emulator / oauthToken field)
            token = raw.get("accessToken") or raw.get("oauthToken", "")
            if token and _is_valid_oauth_token(token):
                expires_at = raw.get("expiresAt", 0)
                if isinstance(expires_at, (int, float)) and expires_at > 1e12:
                    expires_at = int(expires_at / 1000)
                return OAuthTokens(
                    access_token=token,
                    refresh_token=raw.get("refreshToken", ""),
                    expires_at=int(expires_at) if isinstance(expires_at, (int, float)) else 0,
                    scopes=raw.get("scopes", ["user:inference"]),
                )
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Failed to load tokens from %s: %s", path, e)

    return None


class ClaudeCodeAuthProvider(BaseOAuthProvider):
    """OAuth provider for Claude Code subscription-based LLM access."""

    @property
    def provider_name(self) -> str:
        return "Claude Code"

    @property
    def token_path(self) -> Path:
        return CREDENTIALS_PATH

    @property
    def client_id(self) -> str:
        return CLIENT_ID

    @property
    def authorize_url(self) -> str:
        return CLAUDE_AI_AUTHORIZE_URL

    @property
    def token_url(self) -> str:
        return TOKEN_URL

    def get_headers(self, access_token: str) -> dict[str, str]:
        """Build Anthropic API headers with OAuth token + spoofing headers."""
        return build_anthropic_headers(access_token)

    async def get_access_token(self) -> str:
        """Get a valid access token from Claude Code credentials."""
        tokens = self._cached_tokens or _load_claude_code_tokens()
        if tokens is None:
            raise RuntimeError(
                f"No {self.provider_name} OAuth tokens found. "
                "Run 'claude' CLI and login, or use 'decepticon onboard'."
            )
        if tokens.is_expired():
            tokens = await self.refresh_token(tokens)
            self._store.save(self.token_path, tokens)
        self._cached_tokens = tokens
        return tokens.access_token

    def is_authenticated(self) -> bool:
        """Check if valid Claude Code tokens exist."""
        return _load_claude_code_tokens() is not None

    async def start_oauth_flow(self) -> OAuthTokens:
        """Start interactive OAuth 2.0 + PKCE login flow.

        Opens a browser for authorization, starts a local callback server,
        and exchanges the authorization code for tokens.

        In headless environments (no DISPLAY), prints the URL for manual
        browser access and waits for the callback.
        """
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        state = _generate_state()

        # Start local callback server on a random port
        server = HTTPServer(("localhost", 0), _CallbackHandler)
        port = server.server_address[1]
        _CallbackHandler.authorization_code = None
        _CallbackHandler.received_state = None

        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            redirect_uri = f"http://localhost:{port}/callback"
            auth_url = self._build_auth_url(challenge, state, redirect_uri)

            is_headless = not os.environ.get("DISPLAY") and sys.platform != "darwin"

            if is_headless:
                log.info("Headless environment detected. Open this URL manually:")
                print(f"\n  {auth_url}\n")  # noqa: T201
            else:
                log.info("Opening browser for OAuth login...")
                webbrowser.open(auth_url)
                print(f"\nIf the browser didn't open, visit:\n  {auth_url}\n")  # noqa: T201

            # Wait for callback (timeout 5 minutes)
            for _ in range(300):
                if _CallbackHandler.authorization_code is not None:
                    break
                await asyncio.sleep(1)

            if _CallbackHandler.authorization_code is None:
                raise TimeoutError("OAuth callback not received within 5 minutes")

            if _CallbackHandler.received_state != state:
                raise ValueError("OAuth state mismatch — possible CSRF attack")

            # Exchange code for tokens
            tokens = await self._exchange_code(
                code=_CallbackHandler.authorization_code,
                verifier=verifier,
                state=state,
                redirect_uri=redirect_uri,
            )

            self._store.save(self.token_path, tokens)
            log.info("Claude Code OAuth login successful")
            return tokens

        finally:
            server.shutdown()

    def _build_auth_url(self, challenge: str, state: str, redirect_uri: str) -> str:
        """Build the OAuth authorization URL with PKCE parameters."""
        params = {
            "code": "true",
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(OAUTH_SCOPES),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query}"

    async def _exchange_code(
        self,
        code: str,
        verifier: str,
        state: str,
        redirect_uri: str,
    ) -> OAuthTokens:
        """Exchange authorization code for access + refresh tokens."""
        import time

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.token_url,
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": verifier,
                    "state": state,
                },
                headers={"content-type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=int(time.time()) + data.get("expires_in", 3600),
            scopes=data.get("scope", "").split(),
        )
