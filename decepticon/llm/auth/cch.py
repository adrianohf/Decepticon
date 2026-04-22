"""CCH (Claude Code Hash) request signing module.

Implements the xxHash64-based body integrity hash that the real Claude Code
binary computes. The algorithm:
  1. Build the complete request body with ``cch=00000`` as placeholder
  2. Compute ``xxHash64(body_bytes, seed) & 0xFFFFF``
  3. Format as zero-padded 5-character lowercase hex
  4. Replace ``cch=00000`` with the computed value in the body

Reference: not-claude-code-emulator/src/services/cch.ts
"""

from __future__ import annotations

import xxhash

CCH_SEED: int = 0x6E52736AC806831E
CCH_PLACEHOLDER = "cch=00000"
CCH_MASK = 0xFFFFF


def compute_cch(body: str) -> str:
    """Compute the 5-character cch hash from the serialized request body.

    The body must contain the ``cch=00000`` placeholder at this point.
    """
    digest = xxhash.xxh64(body.encode(), seed=CCH_SEED).intdigest()
    return format(digest & CCH_MASK, "05x")


def replace_cch_placeholder(body: str, cch: str) -> str:
    """Replace the ``cch=00000`` placeholder with the computed hash value."""
    return body.replace(CCH_PLACEHOLDER, f"cch={cch}")


def has_cch_placeholder(body: str) -> bool:
    """Check if a body string contains the cch placeholder."""
    return CCH_PLACEHOLDER in body
