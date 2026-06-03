"""Shared fixtures for KG integration tests against live Neo4j.

The fixtures skip every test cleanly when the env vars are not set or
the driver cannot connect, so the integration suite is safe to run in
any environment — it just no-ops on stacks without Neo4j.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

from decepticon.middleware.kg_internal.store import KGStore, KGStoreConfigError

_DEFAULT_TEST_URI = "bolt://localhost:7687"
_DEFAULT_TEST_USER = "neo4j"
_DEFAULT_TEST_PASSWORD = "decepticon-graph"


def _maybe_seed_defaults() -> None:
    """If the developer hasn't set DECEPTICON_NEO4J_* but the compose
    stack is running on localhost, fill in the compose defaults so the
    integration suite "just works" on a normal dev box.

    No-op when any var is already set — explicit values always win.
    """
    if not os.environ.get("DECEPTICON_NEO4J_URI"):
        os.environ.setdefault("DECEPTICON_NEO4J_URI", _DEFAULT_TEST_URI)
    if not os.environ.get("DECEPTICON_NEO4J_USER"):
        os.environ.setdefault("DECEPTICON_NEO4J_USER", _DEFAULT_TEST_USER)
    if not os.environ.get("DECEPTICON_NEO4J_PASSWORD"):
        os.environ.setdefault("DECEPTICON_NEO4J_PASSWORD", _DEFAULT_TEST_PASSWORD)


@pytest.fixture(scope="session")
def kgstore() -> Iterator[KGStore]:
    """A live :class:`KGStore` against compose Neo4j.

    Skips the test when env vars are missing or the driver cannot
    open / round-trip a trivial query.
    """
    _maybe_seed_defaults()
    try:
        store = KGStore.from_env()
    except KGStoreConfigError as exc:
        pytest.skip(f"DECEPTICON_NEO4J_* not configured: {exc}")
    except Exception as exc:
        pytest.skip(f"KGStore construction failed: {exc}")

    # Connectivity smoke. ``schema`` is the reserved label the runner
    # uses, so re-using it here matches production behaviour.
    try:
        store.execute_read("RETURN 1 AS ok", {}, engagement="schema")
    except Exception as exc:  # pragma: no cover — depends on live service
        store.close()
        pytest.skip(f"Neo4j not reachable for KG integration tests: {exc}")

    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def engagement(kgstore: KGStore) -> Iterator[str]:
    """Unique engagement label per test; auto-cleaned post-test."""
    label = f"itest-{uuid.uuid4().hex[:12]}"
    try:
        yield label
    finally:
        # Best-effort cleanup. Reset failures must not mask test
        # assertions, so swallow.
        try:
            kgstore.execute_write(
                "MATCH (n) WHERE n.engagement = $eng DETACH DELETE n",
                {"eng": label},
                engagement=label,
            )
        except Exception:  # pragma: no cover — best-effort
            pass
