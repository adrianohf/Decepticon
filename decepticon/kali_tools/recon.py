"""Recon tool wrappers — subdomain + DNS + HTTP discovery.

subfinder, amass, dnsx, httpx, katana.

Each wrapper writes structured output to ``/tmp/decepticon-kali/...``
so a downstream ``kg_ingest_*`` function can absorb it into the
KnowledgeGraph without re-parsing.
"""

from __future__ import annotations

from langchain_core.tools import tool

from decepticon.kali_tools._common import (
    FlagInjectionError,
    arun_command,
    assert_not_flag,
    format_result,
    scratch_file,
)


def _flag_error(field: str, value: str) -> str:
    """Return an error-envelope JSON for a rejected flag-like argument."""
    import json as _json

    return _json.dumps(
        {
            "ok": False,
            "error": f"rejected flag-like argument: {field}={value!r}",
        },
        indent=2,
    )


@tool
async def subfinder_enum(domain: str, timeout: float = 180.0, sources: str = "") -> str:
    """Run ``subfinder`` for passive subdomain discovery.

    Writes plaintext subdomains to a scratch file and returns the path
    plus a count. Feed the path to ``kg_ingest_subfinder`` to populate
    host + entrypoint nodes.

    Args:
        domain: root domain (e.g. ``example.com``).
        timeout: seconds to wait before killing the scan.
        sources: optional comma-separated subfinder source list.
    """
    try:
        assert_not_flag(domain, field="domain")
        if sources:
            assert_not_flag(sources, field="sources")
    except FlagInjectionError as e:
        return _flag_error("subfinder", str(e))
    out = scratch_file(".txt")
    argv = ["subfinder", "-d", domain, "-silent", "-o", str(out)]
    if sources:
        argv.extend(["-sources", sources])
    result = await arun_command(argv, timeout=timeout)
    count = 0
    if out.exists():
        count = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    result.output_path = str(out)
    return format_result(result, extra={"domain": domain, "subdomains_found": count})


@tool
async def amass_enum(
    domain: str,
    passive: bool = True,
    timeout: float = 600.0,
) -> str:
    """Run OWASP ``amass`` for external asset discovery.

    Defaults to passive enumeration (no direct queries against the
    target) so it's safe to run against scoped engagements.
    """
    try:
        assert_not_flag(domain, field="domain")
    except FlagInjectionError as e:
        return _flag_error("amass", str(e))
    out = scratch_file(".txt")
    argv = ["amass", "enum", "-d", domain, "-o", str(out)]
    if passive:
        argv.append("-passive")
    result = await arun_command(argv, timeout=timeout)
    count = 0
    if out.exists():
        count = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    result.output_path = str(out)
    return format_result(
        result,
        extra={"domain": domain, "mode": "passive" if passive else "active", "found": count},
    )


@tool
async def dnsx_resolve(
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
        return _flag_error("dnsx", "provide hosts_file or hosts")
    try:
        if hosts_file:
            assert_not_flag(hosts_file, field="hosts_file")
        if hosts:
            assert_not_flag(hosts, field="hosts")
        assert_not_flag(record_types, field="record_types")
    except FlagInjectionError as e:
        return _flag_error("dnsx", str(e))
    out = scratch_file(".jsonl")
    argv = ["dnsx", "-json", "-silent", "-t", record_types, "-o", str(out)]
    if hosts_file:
        argv.extend(["-l", hosts_file])
    if hosts:
        # Use -d for inline comma-separated input
        argv.extend(["-d", hosts])
    result = await arun_command(argv, timeout=timeout)
    result.output_path = str(out)
    lines = 0
    if out.exists():
        lines = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    return format_result(result, extra={"records": lines})


@tool
async def httpx_probe(
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
        return _flag_error("httpx", "provide hosts_file or targets")
    try:
        if hosts_file:
            assert_not_flag(hosts_file, field="hosts_file")
        if targets:
            assert_not_flag(targets, field="targets")
    except FlagInjectionError as e:
        return _flag_error("httpx", str(e))
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
    result = await arun_command(argv, timeout=timeout)
    result.output_path = str(out)
    lines = 0
    if out.exists():
        lines = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    return format_result(result, extra={"responses": lines})


@tool
async def katana_crawl(
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
    try:
        assert_not_flag(url, field="url")
    except FlagInjectionError as e:
        return _flag_error("katana", str(e))
    out = scratch_file(".jsonl")
    argv: list[str] = [
        "katana",
        "-u",
        url,
        "-d",
        str(depth),
        "-silent",
        "-json",
        "-o",
        str(out),
    ]
    if js_crawl:
        argv.append("-jc")
    if headless:
        argv.append("-headless")
    result = await arun_command(argv, timeout=timeout)
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
