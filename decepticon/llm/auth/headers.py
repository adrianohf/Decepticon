"""Claude Code spoofing header construction.

Builds the exact set of HTTP headers that the real Claude Code CLI sends
so that the Anthropic API recognises the request as coming from a
subscription-authenticated Claude Code session.

Reference: not-claude-code-emulator/src/services/oauth-client.ts
           not-claude-code-emulator/src/services/request-transformer.ts
"""

from __future__ import annotations

import hashlib

EMULATED_CLI_VERSION = "2.1.87"
FINGERPRINT_SALT = "59cf53e54c78"

REQUIRED_BETAS: list[str] = [
    "claude-code-20250219",
    "oauth-2025-04-20",
    "interleaved-thinking-2025-05-14",
]

BASE_X_HEADERS: dict[str, str] = {
    "x-stainless-timeout": "600",
    "x-stainless-lang": "js",
    "x-stainless-package-version": "0.80.0",
    "x-stainless-os": "Linux",
    "x-stainless-arch": "x64",
    "x-stainless-runtime": "node",
    "x-stainless-runtime-version": "v24.3.0",
    "x-stainless-helper-method": "stream",
    "x-stainless-retry-count": "0",
    "x-app": "cli",
}

BASE_ANTHROPIC_HEADERS: dict[str, str] = {
    "accept": "application/json",
    "content-type": "application/json",
    "anthropic-version": "2023-06-01",
    "anthropic-dangerous-direct-browser-access": "true",
}


def compute_fingerprint(message_text: str, version: str | None = None) -> str:
    """Compute the 3-character fingerprint used in the attribution header.

    Algorithm: SHA256(SALT + msg[4] + msg[7] + msg[20] + version)[:3]
    """
    ver = version or EMULATED_CLI_VERSION
    indices = [4, 7, 20]
    chars = "".join(message_text[i] if i < len(message_text) else "0" for i in indices)

    fingerprint_input = f"{FINGERPRINT_SALT}{chars}{ver}"
    digest = hashlib.sha256(fingerprint_input.encode()).hexdigest()
    return digest[:3]


def get_attribution_header(fingerprint: str) -> str:
    """Build the x-anthropic-billing-header string.

    Format:
      cc_version=VERSION.FINGERPRINT; cc_entrypoint=cli; cch=00000;
    """
    version = f"{EMULATED_CLI_VERSION}.{fingerprint}"
    return f"x-anthropic-billing-header: cc_version={version}; cc_entrypoint=cli; cch=00000;"


def build_anthropic_headers(access_token: str) -> dict[str, str]:
    """Build the full header set for an Anthropic API request using OAuth."""
    headers: dict[str, str] = {}
    headers.update(BASE_ANTHROPIC_HEADERS)
    headers.update(BASE_X_HEADERS)
    headers["authorization"] = f"Bearer {access_token}"
    headers["anthropic-beta"] = ",".join(REQUIRED_BETAS)
    return headers
