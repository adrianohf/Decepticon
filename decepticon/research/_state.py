"""Shared KG state helpers — broken out from ``research/tools.py`` to keep
``scanner_tools`` and ``patch`` free of circular imports.

All modules that want to read/write ``/workspace/kg.json`` should pull
``_load``, ``_save``, and ``_json`` from here. ``tools.py`` re-exports
them under the same private names so existing call sites keep working.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from decepticon.research.graph import (
    DEFAULT_PATH,
    KnowledgeGraph,
    load_graph,
    save_graph,
)


def _kg_path() -> Path:
    """Resolve the knowledge graph path. Override via ``DECEPTICON_KG_PATH``."""
    return Path(os.environ.get("DECEPTICON_KG_PATH", str(DEFAULT_PATH)))


# ── KG load cache ──────────────────────────────────────────────────────
#
# ``_load`` used to re-read the full JSON graph on every @tool call —
# at 10k nodes + 20k edges that's 20–80 ms of Pydantic deserialization
# per tool. We memoize the last-seen graph keyed by ``(path, mtime)``.
# ``_save`` refreshes the cache so subsequent ``_load`` calls see the
# mutated state without touching disk.
_kg_cache: dict[Path, tuple[float, KnowledgeGraph]] = {}


def _load() -> tuple[KnowledgeGraph, Path]:
    path = _kg_path()
    try:
        mtime = path.stat().st_mtime if path.exists() else -1.0
    except OSError:
        mtime = -1.0
    entry = _kg_cache.get(path)
    if entry is not None and entry[0] == mtime:
        return entry[1], path
    graph = load_graph(path)
    _kg_cache[path] = (mtime, graph)
    return graph, path


def _save(graph: KnowledgeGraph, path: Path) -> None:
    save_graph(graph, path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    # Refresh the cache with the just-written graph so the next
    # ``_load`` in the same agent turn sees the mutated state
    # without another round-trip through the JSON parser.
    _kg_cache[path] = (mtime, graph)


def _invalidate_kg_cache() -> None:
    """Drop the KG load cache (tests)."""
    _kg_cache.clear()


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)
