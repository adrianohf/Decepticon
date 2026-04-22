"""Codex OAuth provider — OpenAI subscription-based API access.

Implements OAuth 2.0 + PKCE flow matching the OpenAI Codex CLI.
Tokens are stored at ~/.codex/auth.json.

Note: Codex OAuth tokens obtained via ChatGPT login may only work
through OpenAI's internal proxy, not directly against the API.
For direct API access, use OPENAI_API_KEY instead.

Reference: .omc/research/codex-oauth.md
"""
from __future__ import annotations

import asyncio
import hashlib
import base64
import secrets
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

import httpx

from decepticon.core.logging import get_logger
from decepticon.llm.auth.base import BaseOAuthProvider
from decepticon.llm.auth.token_store import OAuthTokens

log = get_logger("llm.auth.codex")

AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CALLBACK_PORT = 1455
TOKEN_PATH = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"

OAUTH_SCOPES = ["openid", "profile", "email", "offline_access"]


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class _CodexCallbackHandler(BaseHTTPRequestHandler):
    authorization_code: str | None = None
    received_state: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code:
            _CodexCallbackHandler.authorization_code = code
            _CodexCallbackHandler.received_state = state
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Codex authentication successful!</h1>"
                b"<p>You can close this window.</p></body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing authorization code")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress default HTTP server logging."""


class CodexAuthProvider(BaseOAuthProvider):
    """OAuth provider for OpenAI Codex subscription-based LLM access."""

    @property
    def provider_name(self) -> str:
        return "Codex"

    @property
    def token_path(self) -> Path:
        return TOKEN_PATH

    @property
    def client_id(self) -> str:
        return CLIENT_ID

    @property
    def authorize_url(self) -> str:
        return AUTHORIZE_URL

    @property
    def token_url(self) -> str:
        return TOKEN_URL

    def get_headers(self, access_token: str) -> dict[str, str]:
        return {
            "authorization": f"Bearer {access_token}",
            "content-type": "application/json",
        }

    def is_authenticated(self) -> bool:
        """Check if valid Codex tokens exist in ~/.codex/auth.json."""
        return self._load_codex_tokens() is not None

    async def get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        tokens = self._cached_tokens or self._load_codex_tokens()
        if tokens is None:
            raise RuntimeError(
                f"No {self.provider_name} OAuth tokens found at {self.token_path}. "
                f"Run 'decepticon onboard' to authenticate."
            )
        if tokens.is_expired():
            tokens = await self.refresh_token(tokens)
            self._store.save(self.token_path, tokens)
        self._cached_tokens = tokens
        return tokens.access_token

    def _load_codex_tokens(self) -> OAuthTokens | None:
        """Load tokens from Codex auth.json format.

        Codex stores tokens as:
          {"auth_mode": "chatgpt", "tokens": {"access_token": "...", ...}}

        Falls back to the standard TokenStore format if the Codex format
        is not detected.
        """
        import json
        import time

        if not self.token_path.exists():
            return None
        try:
            data = json.loads(self.token_path.read_text())
        except json.JSONDecodeError as e:
            log.warning("Failed to parse %s: %s", self.token_path, e)
            return None

        # Codex native format
        if "tokens" in data and isinstance(data["tokens"], dict):
            t = data["tokens"]
            try:
                return OAuthTokens(
                    access_token=t["access_token"],
                    refresh_token=t.get("refresh_token", ""),
                    expires_at=t.get("expires_at", int(time.time()) + 3600),
                    scopes=t.get("scope", "").split() if t.get("scope") else [],
                )
            except KeyError as e:
                log.warning("Codex auth.json missing key: %s", e)
                return None

        # Fall back to standard TokenStore format (camelCase keys)
        return self._store.load(self.token_path)

    async def start_oauth_flow(self) -> OAuthTokens:
        """Start interactive OAuth 2.0 + PKCE login flow.

        Opens a browser for authorization, starts a local callback server
        on port 1455 (matching Codex's registered redirect URI), and
        exchanges the authorization code for tokens.

        In headless environments (no DISPLAY), prints the URL for manual
        browser access and waits for the callback.
        """
        verifier = _base64url(secrets.token_bytes(32))
        challenge = _base64url(hashlib.sha256(verifier.encode()).digest())
        state = _base64url(secrets.token_bytes(24))

        server = HTTPServer(("localhost", CALLBACK_PORT), _CodexCallbackHandler)
        _CodexCallbackHandler.authorization_code = None
        _CodexCallbackHandler.received_state = None

        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            redirect_uri = f"http://localhost:{CALLBACK_PORT}/auth/callback"
            params = {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": " ".join(OAUTH_SCOPES),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
            query = "&".join(f"{k}={v}" for k, v in params.items())
            auth_url = f"{self.authorize_url}?{query}"

            is_headless = not os.environ.get("DISPLAY") and sys.platform != "darwin"
            if is_headless:
                log.info("Headless environment detected. Open this URL manually:")
                print(f"\n  {auth_url}\n")  # noqa: T201
            else:
                log.info("Opening browser for Codex OAuth login...")
                webbrowser.open(auth_url)
                print(f"\nIf the browser didn't open, visit:\n  {auth_url}\n")  # noqa: T201

            # Wait for callback (timeout 5 minutes)
            for _ in range(300):
                if _CodexCallbackHandler.authorization_code is not None:
                    break
                await asyncio.sleep(1)

            if _CodexCallbackHandler.authorization_code is None:
                raise TimeoutError("OAuth callback not received within 5 minutes")

            if _CodexCallbackHandler.received_state != state:
                raise ValueError("OAuth state mismatch — possible CSRF attack")

            tokens = await self._exchange_code(
                code=_CodexCallbackHandler.authorization_code,
                verifier=verifier,
                state=state,
                redirect_uri=redirect_uri,
            )

            self._store.save(self.token_path, tokens)
            log.info("Codex OAuth login successful")
            return tokens

        finally:
            server.shutdown()

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
