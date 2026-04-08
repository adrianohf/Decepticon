"""LangChain ``@tool`` wrappers that expose the research package to agents.

These are the surfaces the Analyst (and optionally the Orchestrator)
exercise to drive vulnerability research:

- ``kg_*``         — CRUD + query over the knowledge graph
- ``cve_*``        — NVD/OSV/EPSS intelligence lookup
- ``ingest_sarif`` — lift any SARIF file on disk into the graph
- ``plan_attack_chains`` — ranked multi-hop exploit paths
- ``fuzz_*``       — harness synthesis + crash recording helpers

Every tool returns a compact, JSON-serialisable string so it fits the
LangChain tool return contract and keeps LLM token usage low.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.core.logging import get_logger
from decepticon.research import cve as cve_mod
from decepticon.research import fuzz as fuzz_mod
from decepticon.research.chain import plan_chains, promote_chain
from decepticon.research.graph import (
    DEFAULT_PATH,
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
    load_graph,
    save_graph,
)
from decepticon.research.sarif import ingest_sarif_file

log = get_logger("research.tools")


# ── Helpers ─────────────────────────────────────────────────────────────


def _kg_path() -> Path:
    """Resolve the knowledge graph path. Override via ``DECEPTICON_KG_PATH``."""
    import os

    return Path(os.environ.get("DECEPTICON_KG_PATH", str(DEFAULT_PATH)))


def _load() -> tuple[KnowledgeGraph, Path]:
    path = _kg_path()
    return load_graph(path), path


def _save(graph: KnowledgeGraph, path: Path) -> None:
    save_graph(graph, path)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _parse_props(props_json: str) -> dict[str, Any]:
    if not props_json:
        return {}
    try:
        parsed = json.loads(props_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"props must be valid JSON: {e}") from None
    if not isinstance(parsed, dict):
        raise ValueError("props must be a JSON object")
    return parsed


# ── Knowledge graph tools ───────────────────────────────────────────────


@tool
def kg_add_node(kind: str, label: str, props: str = "{}") -> str:
    """Insert or update a node in the engagement knowledge graph.

    WHEN TO USE: Every time you observe an asset, vulnerability, credential,
    entrypoint, crown jewel, or code location. The graph persists across
    Ralph iterations, so a node you add now is queryable by the next
    fresh-context agent.

    NODE KINDS: host, service, url, repo, file, code_location, vulnerability,
    cve, finding, credential, secret, user, entrypoint, crown_jewel, chain,
    hypothesis.

    IMPORTANT: Use ``props`` to store severity, file path, port, cwe, cvss,
    etc. Supply a deterministic ``key`` inside props for deduplication
    (e.g. ``"key": "10.0.0.1:443/tcp"``).

    Args:
        kind: Node type (see NODE KINDS above).
        label: Human-readable label shown in graph summaries.
        props: JSON object with extra fields. Example:
            ``{"severity": "high", "cwe": ["CWE-89"], "file": "app.py", "line": 42}``

    Returns:
        JSON with the created/updated node id and stats.
    """
    try:
        node_kind = NodeKind(kind)
    except ValueError:
        return _json({"error": f"unknown kind: {kind}", "valid": [k.value for k in NodeKind]})
    parsed = _parse_props(props)
    graph, path = _load()
    node = graph.upsert_node(Node.make(node_kind, label, **parsed))
    _save(graph, path)
    return _json(
        {"id": node.id, "kind": node.kind.value, "label": node.label, "stats": graph.stats()}
    )


@tool
def kg_add_edge(src: str, dst: str, kind: str, weight: float = 1.0) -> str:
    """Connect two nodes with a typed, weighted edge.

    WHEN TO USE: After adding nodes, connect them to express relationships
    the chain planner can walk: ``runs_on``, ``has_vuln``, ``enables``,
    ``leaks``, ``grants``, ``chains_to``, etc.

    WEIGHT guides the chain planner — lower = easier to exploit. Defaults
    to 1.0. Use 0.3 for trivial wins, 2.0 for painful pivots.

    EDGE KINDS: runs_on, exposes, has_vuln, defined_in, located_at,
    affected_by, mapped_to, auth_as, grants, leaks, enables, chains_to,
    reaches, starts_at, contains, validates.

    Args:
        src: Source node id (from kg_add_node return value).
        dst: Destination node id.
        kind: Edge type.
        weight: Traversal cost (lower = easier exploitation).

    Returns:
        JSON with edge id and updated graph stats.
    """
    try:
        edge_kind = EdgeKind(kind)
    except ValueError:
        return _json({"error": f"unknown edge kind: {kind}", "valid": [k.value for k in EdgeKind]})
    graph, path = _load()
    if src not in graph.nodes or dst not in graph.nodes:
        return _json(
            {
                "error": "src or dst not in graph",
                "src_present": src in graph.nodes,
                "dst_present": dst in graph.nodes,
            }
        )
    edge = graph.upsert_edge(Edge.make(src, dst, edge_kind, weight=weight))
    _save(graph, path)
    return _json({"id": edge.id, "kind": edge.kind.value, "stats": graph.stats()})


@tool
def kg_query(kind: str = "", min_severity: str = "", limit: int = 25) -> str:
    """Query the knowledge graph for nodes matching kind / severity.

    WHEN TO USE: At the start of any iteration to discover what's already
    known. Before running a scanner, check if the target is already
    enumerated. Before exploiting, check for existing finding nodes.

    Args:
        kind: Node kind filter (empty = all kinds).
        min_severity: For vulnerability nodes only. Empty, low, medium,
            high, or critical. If set, only vulns meeting the bar are
            returned.
        limit: Max nodes to return (default 25).

    Returns:
        JSON list of matching nodes with their core fields and id.
    """
    graph, _ = _load()
    if min_severity:
        try:
            sev = Severity(min_severity.lower())
        except ValueError:
            return _json({"error": f"bad severity: {min_severity}"})
        nodes = graph.vulnerabilities_by_severity(sev)
    elif kind:
        try:
            node_kind = NodeKind(kind)
        except ValueError:
            return _json({"error": f"unknown kind: {kind}"})
        nodes = graph.by_kind(node_kind)
    else:
        nodes = list(graph.nodes.values())

    return _json(
        {
            "total": len(nodes),
            "returned": min(len(nodes), limit),
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind.value,
                    "label": n.label,
                    "props": n.props,
                }
                for n in nodes[:limit]
            ],
        }
    )


@tool
def kg_neighbors(node_id: str, direction: str = "out", edge_kind: str = "") -> str:
    """Walk one hop out from a node to see what it connects to.

    Args:
        node_id: Source node id.
        direction: "out" (default), "in", or "both".
        edge_kind: Optional edge-kind filter.

    Returns:
        JSON list of {edge, neighbor} pairs.
    """
    graph, _ = _load()
    if node_id not in graph.nodes:
        return _json({"error": "node not found", "id": node_id})
    filter_kind: EdgeKind | None = None
    if edge_kind:
        try:
            filter_kind = EdgeKind(edge_kind)
        except ValueError:
            return _json({"error": f"unknown edge kind: {edge_kind}"})
    neighbors = graph.neighbors(node_id, edge_kind=filter_kind, direction=direction)
    return _json(
        [
            {
                "edge_kind": e.kind.value,
                "edge_weight": e.weight,
                "neighbor_id": n.id,
                "neighbor_kind": n.kind.value,
                "neighbor_label": n.label,
            }
            for e, n in neighbors
        ]
    )


@tool
def kg_stats() -> str:
    """Return counts of nodes and edges by kind. Cheapest way to sanity check
    graph state at iteration start. Returns JSON stats dict."""
    graph, path = _load()
    return _json({"path": str(path), **graph.stats()})


# ── CVE intelligence ────────────────────────────────────────────────────


@tool
async def cve_lookup(cve_ids: str) -> str:
    """Look up CVEs against NVD + EPSS with real-world exploitability scoring.

    WHEN TO USE: Whenever you find a service version (nmap -sV),
    dependency (package.json, requirements.txt, Cargo.lock), or CVE ID
    from any source. Returns a ranked list: CVEs with high CVSS *and*
    high EPSS (or KEV listing) bubble to the top.

    The composite ``score`` blends:
    - CVSS base (0-10)
    - EPSS probability (log-scaled)
    - CISA KEV membership (floors score at 9.0)

    Args:
        cve_ids: Comma-separated CVE IDs, e.g. ``"CVE-2024-12345,CVE-2023-99999"``.

    Returns:
        JSON list of exploitability records, highest score first.
    """
    ids = [c.strip() for c in cve_ids.split(",") if c.strip()]
    if not ids:
        return _json({"error": "no CVE IDs provided"})
    records = await cve_mod.lookup_cves(ids)
    return _json([r.to_dict() for r in records])


@tool
async def cve_by_package(package: str, version: str, ecosystem: str = "PyPI") -> str:
    """Query OSV for CVEs affecting ``package@version`` in an ecosystem.

    WHEN TO USE: After reading a manifest file (requirements.txt,
    package.json, go.sum, Cargo.lock). Pair with ``cve_lookup`` to score
    the results and prioritise bounty-worthy targets.

    Args:
        package: Package name (exact, case-sensitive).
        version: Installed version string.
        ecosystem: One of PyPI, npm, crates.io, Go, Maven, RubyGems,
            NuGet, Packagist, Pub, Hex.

    Returns:
        JSON list of vulnerability IDs (CVE/GHSA). Empty if the package
        version is clean (or the OSV API was unreachable).
    """
    ids = await cve_mod.lookup_package(package, version, ecosystem)
    return _json({"package": package, "version": version, "ecosystem": ecosystem, "ids": ids})


# ── Static analysis ingestion ───────────────────────────────────────────


@tool
def kg_ingest_sarif(path: str, scanner_hint: str = "") -> str:
    """Ingest a SARIF report (semgrep, bandit, gitleaks, trivy, codeql) into the graph.

    WHEN TO USE: After running any SARIF-emitting scanner. Lifts every
    ``result`` in the file into a Vulnerability node linked to its
    CodeLocation and File, so the chain planner can reason about
    source-level bugs.

    EXAMPLES:
        semgrep --sarif --config=auto /workspace/src > /workspace/semgrep.sarif
        bandit -r /workspace/src -f sarif -o /workspace/bandit.sarif
        gitleaks detect --source /workspace/src --report-format sarif --report-path /workspace/gitleaks.sarif

    Args:
        path: Absolute path to the SARIF file (must be inside the sandbox
            workspace or host bind mount).
        scanner_hint: Override the scanner name. Useful when the SARIF
            driver name is anonymised or mislabeled.

    Returns:
        JSON with the ingested result count and updated graph stats.
    """
    graph, out = _load()
    hint = scanner_hint or None
    n = ingest_sarif_file(path, graph, scanner_hint=hint)
    _save(graph, out)
    return _json({"ingested": n, "stats": graph.stats()})


# ── Chain planner ──────────────────────────────────────────────────────


@tool
def plan_attack_chains(
    max_depth: int = 8, max_cost: float = 20.0, top_k: int = 10, promote: bool = False
) -> str:
    """Enumerate multi-hop exploit chains from entrypoints to crown jewels.

    WHEN TO USE: After you've added ENTRYPOINT nodes (exposed public
    surfaces) and CROWN_JEWEL nodes (bounty-worthy targets) and connected
    vulns between them with ``enables``/``leaks``/``grants`` edges. The
    planner walks the graph with Dijkstra and returns the cheapest
    complete paths.

    COST MODEL: lower is better. Critical vulns shrink cost (0.4x),
    validated PoCs shrink further (0.5x), high edge weight grows it.

    Args:
        max_depth: Max hops per chain (default 8).
        max_cost: Discard paths exceeding this total cost (default 20).
        top_k: Return the top-K cheapest chains (default 10).
        promote: If true, persist each computed chain as a ``chain`` node
            in the graph so future queries can reference it.

    Returns:
        JSON list of chains with entrypoint, crown jewel, hop sequence,
        and total cost.
    """
    graph, path = _load()
    chains = plan_chains(graph, max_depth=max_depth, max_cost=max_cost, top_k=top_k)
    promoted_ids: list[str] = []
    if promote:
        for chain in chains:
            promoted_ids.append(promote_chain(graph, chain).id)
        _save(graph, path)
    return _json(
        {
            "count": len(chains),
            "promoted": promoted_ids if promote else [],
            "chains": [c.to_dict() for c in chains],
        }
    )


# ── Fuzzing ─────────────────────────────────────────────────────────────


@tool
def fuzz_classify(root: str) -> str:
    """Classify a source tree and recommend a fuzzer engine.

    Returns the best-guess language, the default fuzz engine for it, and
    up to 20 candidate entry functions (files matching main/parse/decode/
    deserialize/handle/fuzz).

    Args:
        root: Absolute path to the source root (repo checkout or tarball
            extraction dir).
    """
    tp = fuzz_mod.classify_target(root)
    return _json(
        {
            "root": str(tp.root),
            "language": tp.language,
            "engine": tp.engine.value if tp.engine else None,
            "entry_candidates": [str(p) for p in tp.entry_candidates],
            "notes": tp.notes,
        }
    )


@tool
def fuzz_harness(engine: str, target: str, entry: str = "parse") -> str:
    """Emit a minimal starter harness for a target + engine pair.

    ENGINES: libfuzzer, afl++, honggfuzz, jazzer, atheris, cargo-fuzz,
    go-fuzz, boofuzz. Returns ready-to-compile/run source code.

    Args:
        engine: Fuzzer engine name.
        target: Module / library under test (used in template strings).
        entry: Entry function / symbol to attach the harness to.
    """
    try:
        eng = fuzz_mod.Engine(engine)
    except ValueError:
        return _json(
            {"error": f"unknown engine: {engine}", "valid": [e.value for e in fuzz_mod.Engine]}
        )
    try:
        src = fuzz_mod.harness_for(eng, target, entry)
    except ValueError as e:
        return _json({"error": str(e)})
    return _json({"engine": eng.value, "source": src})


@tool
def fuzz_record_crash(log: str, engine: str) -> str:
    """Parse an ASan/UBSan log, extract the crash, and persist it as a vuln.

    WHEN TO USE: Immediately after a fuzzer reports a crash. Paste the
    last ~1K lines of sanitizer output as ``log``. The parser extracts
    the crash kind (heap-buffer-overflow, double-free, etc.), severity,
    file:line, and the first 15 stack frames, then writes a Vulnerability
    + CodeLocation pair into the graph.

    Args:
        log: Raw sanitizer output from the fuzzer run.
        engine: Fuzzer engine that produced the crash.

    Returns:
        JSON record of the parsed crash or an error if no crash signature
        was recognised.
    """
    try:
        eng = fuzz_mod.Engine(engine)
    except ValueError:
        return _json({"error": f"unknown engine: {engine}"})
    crash = fuzz_mod.parse_asan(log)
    if crash is None:
        return _json({"error": "no ASan/UBSan signature found in log"})
    graph, path = _load()
    vuln = fuzz_mod.record_crash(graph, crash, engine=eng)
    _save(graph, path)
    return _json(
        {
            "vuln_id": vuln.id,
            "severity": crash.severity.value,
            "sanitizer": crash.sanitizer,
            "kind": crash.kind,
            "file": crash.file,
            "line": crash.line,
            "stack_depth": len(crash.stack),
        }
    )


# ── PoC validation ─────────────────────────────────────────────────────


@tool
async def validate_finding(
    vuln_id: str,
    poc_command: str,
    success_patterns: str,
    negative_command: str = "",
    negative_patterns: str = "",
    cvss_vector: str = "",
) -> str:
    """Run a PoC inside the sandbox and mark the vuln validated on hit.

    WHEN TO USE: After identifying a vulnerability, craft a minimal
    reproducer and run it here. The validator applies ZFP (zero false
    positives) by requiring a negative control: if the same request
    without the payload *also* fires the success pattern, the result is
    demoted.

    SUCCESS PATTERNS are Python regexes (DOTALL + IGNORECASE). Use simple
    substrings when you don't need regex power.

    CVSS_VECTOR example: ``"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"``
    If provided, the base score is computed and written back onto the
    vuln node.

    Args:
        vuln_id: Graph id of the vulnerability node to validate.
        poc_command: Bash command that exercises the vulnerability.
        success_patterns: Comma-separated list of regexes to match in stdout.
        negative_command: Optional baseline command (same request without payload).
        negative_patterns: Comma-separated regexes expected in the baseline.
        cvss_vector: Optional CVSS v3.1 vector string.

    Returns:
        JSON validation record including success signals, negative
        control hits, stdout excerpt, and CVSS score if provided.
    """
    from decepticon.research.poc import (
        AC,
        AV,
        PR,
        UI,
        CVSSVector,
        Impact,
        Scope,
        sandbox_runner,
        validate_poc,
    )
    from decepticon.tools.bash.bash import get_sandbox

    sandbox = get_sandbox()
    if sandbox is None:
        return _json({"error": "DockerSandbox not initialized"})

    def _split(s: str) -> list[str]:
        return [p.strip() for p in s.split(",") if p.strip()]

    cvss: CVSSVector | None = None
    if cvss_vector:
        try:
            parts = {kv.split(":")[0]: kv.split(":")[1] for kv in cvss_vector.split("/")[1:]}
            cvss = CVSSVector(
                av=AV(parts.get("AV", "N")),
                ac=AC(parts.get("AC", "L")),
                pr=PR(parts.get("PR", "N")),
                ui=UI(parts.get("UI", "N")),
                scope=Scope(parts.get("S", "U")),
                c=Impact(parts.get("C", "H")),
                i=Impact(parts.get("I", "H")),
                a=Impact(parts.get("A", "H")),
            )
        except (ValueError, KeyError, IndexError) as e:
            return _json({"error": f"bad CVSS vector: {e}"})

    graph, path = _load()
    runner = sandbox_runner(sandbox)
    result = await validate_poc(
        vuln_id=vuln_id,
        poc_command=poc_command,
        success_patterns=_split(success_patterns),
        runner=runner,
        negative_command=negative_command or None,
        negative_patterns=_split(negative_patterns) if negative_patterns else None,
        cvss=cvss,
        graph=graph,
    )
    _save(graph, path)
    return _json(result.to_dict())


# ── Public tool list ────────────────────────────────────────────────────

RESEARCH_TOOLS = [
    kg_add_node,
    kg_add_edge,
    kg_query,
    kg_neighbors,
    kg_stats,
    kg_ingest_sarif,
    cve_lookup,
    cve_by_package,
    plan_attack_chains,
    fuzz_classify,
    fuzz_harness,
    fuzz_record_crash,
    validate_finding,
]
