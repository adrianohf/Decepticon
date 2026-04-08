"""LangChain @tool wrappers for the references package."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from decepticon.references.catalog import (
    REFERENCES,
    references_by_category,
    references_for_topic,
    suggest_for_finding,
)
from decepticon.references.fetch import (
    cache_status,
    ensure_cached,
    search_cache,
)
from decepticon.references.payloads import (
    BUNDLED_PAYLOADS,
    search_payloads,
)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@tool
def ref_list(category: str = "") -> str:
    """List catalogued external reference repositories.

    Filter by ``category``: report-corpus | payload-library | cheat-sheet |
    reference-agent | tool-index | cve-poc | methodology. Empty = all.
    """
    items = references_by_category(category) if category else list(REFERENCES)
    return _json({"count": len(items), "references": [r.to_dict() for r in items]})


@tool
def ref_suggest(vuln_class: str = "", goal: str = "") -> str:
    """Suggest the best reference repositories for a given vuln class or goal.

    Examples:
        ref_suggest(vuln_class="ssrf")
        ref_suggest(goal="recon")
    """
    picks = suggest_for_finding(vuln_class or None, goal or None)
    return _json({"count": len(picks), "references": [r.to_dict() for r in picks]})


@tool
def ref_topic(topic: str) -> str:
    """Return reference repos whose topic list contains the given topic."""
    items = references_for_topic(topic)
    return _json({"topic": topic, "count": len(items), "references": [r.to_dict() for r in items]})


@tool
def ref_fetch(slug: str) -> str:
    """Clone (or update) a reference repository into the sandbox cache.

    Cache path: ``/workspace/.references/<slug>/``. Subsequent calls
    run ``git pull`` to stay current. Returns the cache status.
    """
    try:
        status = ensure_cached(slug)
    except KeyError as e:
        return _json({"error": str(e)})
    return _json(status.to_dict())


@tool
def ref_status(slug: str = "") -> str:
    """Report whether a reference is cached locally and how large it is.

    Pass an empty slug to return the full cache map.
    """
    if slug:
        try:
            return _json(cache_status(slug).to_dict())
        except KeyError as e:
            return _json({"error": str(e)})
    rows = []
    for ref in REFERENCES:
        rows.append(cache_status(ref.slug).to_dict())
    return _json({"count": len(rows), "cache": rows})


@tool
def ref_grep(slug: str, pattern: str, max_results: int = 30) -> str:
    """Grep a cached reference repo for a pattern.

    Uses ripgrep if available, then grep, then pure-Python fallback.
    Returns the first ``max_results`` matches as (file, line, snippet).
    """
    try:
        hits = search_cache(slug, pattern, max_results=max_results)
    except KeyError as e:
        return _json({"error": str(e)})
    return _json(
        {
            "slug": slug,
            "pattern": pattern,
            "count": len(hits),
            "hits": [{"file": fp, "line": ln, "snippet": snip} for fp, ln, snip in hits],
        }
    )


@tool
def payload_search(vuln_class: str = "", keyword: str = "") -> str:
    """Search the offline-bundled payload library.

    Instant (no network) — returns canonical payloads for sqli, ssrf,
    xss, ssti, deser, rce, xxe, idor, jwt, oauth, lfi, cmdi, graphql,
    prompt-injection, proto-pollution.

    Example:
        payload_search(vuln_class="ssrf", keyword="imds")
    """
    if not vuln_class and not keyword:
        # List everything, capped
        items = list(BUNDLED_PAYLOADS)[:80]
    else:
        items = search_payloads(vuln_class=vuln_class or None, keyword=keyword or None)
    return _json({"count": len(items), "payloads": [p.to_dict() for p in items]})


@tool
def payload_classes() -> str:
    """List every vuln class with a bundled payload set + count."""
    classes: dict[str, int] = {}
    for p in BUNDLED_PAYLOADS:
        classes[p.vuln_class] = classes.get(p.vuln_class, 0) + 1
    return _json(
        {
            "count": len(classes),
            "classes": [{"vuln_class": k, "count": v} for k, v in sorted(classes.items())],
        }
    )


REFERENCES_TOOLS = [
    ref_list,
    ref_suggest,
    ref_topic,
    ref_fetch,
    ref_status,
    ref_grep,
    payload_search,
    payload_classes,
]
