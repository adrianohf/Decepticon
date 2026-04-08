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
from decepticon.references.cve_poc_index import lookup_poc
from decepticon.references.fetch import (
    cache_status,
    ensure_cached,
    search_cache,
)
from decepticon.references.h1_corpus import search as h1_search_corpus
from decepticon.references.hydrate import format_report, hydrate_all
from decepticon.references.killchain import (
    lookup as killchain_lookup_entries,
)
from decepticon.references.killchain import (
    suggest as killchain_suggest_entries,
)
from decepticon.references.methodology import lookup as methodology_lookup_chapters
from decepticon.references.oneliners import search as oneliner_search_recipes
from decepticon.references.payloads import (
    BUNDLED_PAYLOADS,
    search_payloads,
)
from decepticon.references.payloads_ingest import merged_payloads, search_merged


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
def payload_search(vuln_class: str = "", keyword: str = "", limit: int = 120) -> str:
    """Search the payload library (bundled + ingested PayloadsAllTheThings).

    Instant (no network). Returns committed curated payloads first,
    then any rows ingested from a cached ``payloads-all-the-things``
    clone. Covers every class from sqli / ssrf / xss / ssti / deser /
    rce / xxe / idor / jwt / oauth / lfi / cmdi / graphql /
    prompt-injection / proto-pollution plus any extra class discovered
    in the cached repo.

    Example:
        payload_search(vuln_class="ssrf", keyword="imds")
    """
    if not vuln_class and not keyword:
        items = list(merged_payloads())[:limit]
    else:
        items = search_merged(
            vuln_class=vuln_class or None,
            keyword=keyword or None,
            limit=limit,
        )
        if not items:
            # Fallback to the curated-only search so the agent still
            # gets the bundled rows when the ingest cache is absent.
            items = search_payloads(vuln_class=vuln_class or None, keyword=keyword or None)
    return _json({"count": len(items), "payloads": [p.to_dict() for p in items]})


@tool
def payload_classes() -> str:
    """List every vuln class with payload coverage (bundled + ingested)."""
    classes: dict[str, int] = {}
    for p in merged_payloads():
        classes[p.vuln_class] = classes.get(p.vuln_class, 0) + 1
    if not classes:
        for p in BUNDLED_PAYLOADS:
            classes[p.vuln_class] = classes.get(p.vuln_class, 0) + 1
    return _json(
        {
            "count": len(classes),
            "classes": [{"vuln_class": k, "count": v} for k, v in sorted(classes.items())],
        }
    )


@tool
def cve_poc_lookup(cve_id: str) -> str:
    """Return known public PoC URLs for a CVE.

    Reads the local ``cve_poc_index`` populated from the ``trickest-cve``
    and ``penetration-testing-poc`` reference caches. Returns an empty
    list when the caches are not hydrated.

    Example:
        cve_poc_lookup("CVE-2021-44228")
    """
    urls = lookup_poc(cve_id)
    return _json({"cve_id": cve_id.upper(), "count": len(urls), "poc_urls": urls})


@tool
def h1_search(
    cwe: str = "",
    keyword: str = "",
    program: str = "",
    severity: str = "",
    min_bounty: float = 0.0,
    limit: int = 15,
) -> str:
    """Search the HackerOne disclosed-report corpus for prior art.

    Filters the cached ``hackerone-reports`` repo by CWE, free-text
    keyword, program name, severity, and minimum bounty. Great for
    answering "has anyone reported this bug class before, and what did
    it pay?" before writing up a finding.

    Example:
        h1_search(cwe="CWE-918", min_bounty=1000)
        h1_search(keyword="account takeover", severity="high")
    """
    hits = h1_search_corpus(
        cwe=cwe or None,
        keyword=keyword or None,
        program=program or None,
        severity=severity or None,
        min_bounty=min_bounty,
        limit=limit,
    )
    return _json({"count": len(hits), "reports": [r.to_dict() for r in hits]})


@tool
def oneliner_search(topic: str, limit: int = 10) -> str:
    """Look up shell / tooling one-liners from the-book-of-secret-knowledge.

    Substring-matches the topic against recipe heading chains and
    descriptions. Returns the matching recipes with their command
    block and heading trail.

    Example:
        oneliner_search("tcpdump filter ssl")
        oneliner_search("ssh tunnel")
    """
    recipes = oneliner_search_recipes(topic, limit=limit)
    return _json({"count": len(recipes), "recipes": [r.to_dict() for r in recipes]})


@tool
def killchain_lookup(phase: str, limit: int = 20) -> str:
    """List red-team tools for a kill-chain phase.

    Phase can be any MITRE ATT&CK tactic: recon, weaponization,
    delivery, exploitation, persistence, privilege-escalation,
    defense-evasion, credential-access, discovery, lateral-movement,
    collection, command-and-control, exfiltration, impact.

    Data source is the committed ``killchain.yaml`` overlaid by the
    cached ``redteam-tools`` README when present.
    """
    entries = killchain_lookup_entries(phase, limit=limit)
    return _json(
        {
            "phase": phase,
            "count": len(entries),
            "tools": [e.to_dict() for e in entries],
        }
    )


@tool
def killchain_suggest(objective: str, limit: int = 10) -> str:
    """Suggest tools for an objective description via keyword match.

    Example:
        killchain_suggest("enumerate SMB shares and users")
        killchain_suggest("crack kerberos tickets")
    """
    entries = killchain_suggest_entries(objective, limit=limit)
    return _json(
        {
            "objective": objective,
            "count": len(entries),
            "tools": [e.to_dict() for e in entries],
        }
    )


@tool
def methodology_lookup(vuln_class: str, excerpt_chars: int = 1800) -> str:
    """Return methodology chapters from AllAboutBugBounty for a vuln class.

    ``vuln_class`` can be ``ssrf``, ``idor``, ``ato``, ``oauth``,
    ``rce``, ``sqli``, ``xss``, ``2fa-bypass``, etc. Returns raw
    markdown excerpts from the matching chapter(s).
    """
    chapters = methodology_lookup_chapters(vuln_class, excerpt_chars=excerpt_chars)
    return _json(
        {
            "vuln_class": vuln_class,
            "count": len(chapters),
            "chapters": chapters,
        }
    )


@tool
def references_hydrate() -> str:
    """Clone or update every indexed reference repo (one-shot hydration).

    Runs ``git clone --depth 1`` or ``git pull`` for PayloadsAllTheThings,
    trickest/cve, Penetration_Testing_POC, hackerone-reports,
    the-book-of-secret-knowledge, RedTeam-Tools, and AllAboutBugBounty.
    After the clones land, rebuilds the CVE→PoC JSON index. Safe to
    call repeatedly — existing clones are fast-forwarded.
    """
    results = hydrate_all()
    return _json(
        {
            "report": format_report(results),
            "results": [r.to_dict() for r in results],
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
    cve_poc_lookup,
    h1_search,
    oneliner_search,
    killchain_lookup,
    killchain_suggest,
    methodology_lookup,
    references_hydrate,
]
