"""Recon tool wrappers — subdomain + DNS + HTTP discovery.

subfinder, amass, dnsx, httpx, katana.

Each wrapper writes structured output to ``/tmp/decepticon-kali/...``
so a downstream ``kg_ingest_*`` function can absorb it into the
KnowledgeGraph without re-parsing.
"""

from __future__ import annotations

from langchain_core.tools import tool

from decepticon.kali_tools._common import (
    format_result,
    run_command,
    scratch_file,
)


@tool
def subfinder_enum(domain: str, timeout: float = 180.0, sources: str = "") -> str:
    """Run ``subfinder`` for passive subdomain discovery.

    Writes plaintext subdomains to a scratch file and returns the path
    plus a count. Feed the path to ``kg_ingest_subfinder`` to populate
    host + entrypoint nodes.

    Args:
        domain: root domain (e.g. ``example.com``).
        timeout: seconds to wait before killing the scan.
        sources: optional comma-separated subfinder source list.
    """
    out = scratch_file(".txt")
    argv = ["subfinder", "-d", domain, "-silent", "-o", str(out)]
    if sources:
        argv.extend(["-sources", sources])
    result = run_command(argv, timeout=timeout)
    count = 0
    if out.exists():
        count = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    result.output_path = str(out)
    return format_result(result, extra={"domain": domain, "subdomains_found": count})


@tool
def amass_enum(
    domain: str,
    passive: bool = True,
    timeout: float = 600.0,
) -> str:
    """Run OWASP ``amass`` for external asset discovery.

    Defaults to passive enumeration (no direct queries against the
    target) so it's safe to run against scoped engagements.
    """
    out = scratch_file(".txt")
    argv = ["amass", "enum", "-d", domain, "-o", str(out)]
    if passive:
        argv.append("-passive")
    result = run_command(argv, timeout=timeout)
    count = 0
    if out.exists():
        count = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    result.output_path = str(out)
    return format_result(
        result,
        extra={"domain": domain, "mode": "passive" if passive else "active", "found": count},
    )


@tool
def dnsx_resolve(
    hosts_file: str = "",
    hosts: str = "",
    record_types: str = "a,aaaa,cname",
    timeout: float = 180.0,
) -> str:
    """Run ``dnsx`` to resolve a list of hostnames.

    Exactly one of ``hosts_file`` (path) or ``hosts`` (comma-separated
    inline list) must be provided. Outputs JSONL with resolution
    details. Feed the output path to ``kg_ingest_dnsx``.
    """
    if not hosts_file and not hosts:
        return format_result(
            run_command(["dnsx", "--help"], timeout=5.0),
            extra={"error": "provide hosts_file or hosts"},
        )
    out = scratch_file(".jsonl")
    argv = ["dnsx", "-json", "-silent", "-t", record_types, "-o", str(out)]
    if hosts_file:
        argv.extend(["-l", hosts_file])
    if hosts:
        # Use -d for inline comma-separated input
        argv.extend(["-d", hosts])
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    lines = 0
    if out.exists():
        lines = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    return format_result(result, extra={"records": lines})


@tool
def httpx_probe(
    hosts_file: str = "",
    targets: str = "",
    status_code: bool = True,
    tech_detect: bool = True,
    title: bool = True,
    timeout: float = 240.0,
) -> str:
    """Run ``httpx`` against a list of hosts to fingerprint web services.

    Output is JSONL. Feed the output path to ``kg_ingest_httpx_jsonl``
    to create host/service/entrypoint nodes in one call.
    """
    if not hosts_file and not targets:
        return format_result(
            run_command(["httpx", "-version"], timeout=5.0),
            extra={"error": "provide hosts_file or targets"},
        )
    out = scratch_file(".jsonl")
    argv = ["httpx", "-json", "-silent", "-no-color", "-o", str(out)]
    if status_code:
        argv.append("-status-code")
    if tech_detect:
        argv.append("-tech-detect")
    if title:
        argv.append("-title")
    if hosts_file:
        argv.extend(["-l", hosts_file])
    if targets:
        argv.extend(["-u", targets])
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    lines = 0
    if out.exists():
        lines = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    return format_result(result, extra={"responses": lines})


@tool
def katana_crawl(
    url: str,
    depth: int = 3,
    js_crawl: bool = True,
    headless: bool = False,
    timeout: float = 600.0,
) -> str:
    """Run ``katana`` for modern web crawling / attack-surface discovery.

    Writes crawled URLs as JSONL — hand the output path to
    ``kg_ingest_katana`` (see ``research/tools.py``) to turn the crawl
    into entrypoint nodes.
    """
    out = scratch_file(".jsonl")
    argv = [
        "katana",
        "-u",
        url,
        "-d",
        str(depth),
        "-jc" if js_crawl else "-d",  # -jc = enable JS crawl
        "-silent",
        "-json",
        "-o",
        str(out),
    ]
    if js_crawl:
        argv = [a for a in argv if a != "-d" or True]  # keep -d for depth
    if headless:
        argv.append("-headless")
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    lines = 0
    if out.exists():
        lines = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    return format_result(result, extra={"urls_crawled": lines})


RECON_TOOLS = [
    subfinder_enum,
    amass_enum,
    dnsx_resolve,
    httpx_probe,
    katana_crawl,
]

__all__ = ["RECON_TOOLS"]
