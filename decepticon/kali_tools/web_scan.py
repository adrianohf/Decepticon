"""Web scanner wrappers — nuclei, nikto, ffuf, gobuster, dirsearch,
testssl, whatweb, wafw00f."""

from __future__ import annotations

from langchain_core.tools import tool

from decepticon.kali_tools._common import (
    format_result,
    run_command,
    scratch_file,
)


@tool
def nuclei_scan(
    target: str,
    templates: str = "",
    severity: str = "",
    rate_limit: int = 150,
    timeout: float = 1800.0,
) -> str:
    """Run ``nuclei`` template-based vuln scanner against a target.

    Output is JSONL. Feed the output path to ``kg_ingest_nuclei_jsonl``
    to create vulnerability + code-location nodes.

    Args:
        target: URL or host to scan.
        templates: optional path / tag filter (``cves,misconfig``).
        severity: filter (``critical,high`` etc.).
        rate_limit: requests per second.
    """
    out = scratch_file(".jsonl")
    argv = [
        "nuclei",
        "-u",
        target,
        "-silent",
        "-jsonl",
        "-o",
        str(out),
        "-rate-limit",
        str(rate_limit),
        "-stats-json",
        "-no-color",
    ]
    if templates:
        argv.extend(["-t", templates])
    if severity:
        argv.extend(["-severity", severity])
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    lines = 0
    if out.exists():
        lines = sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())
    return format_result(result, extra={"findings": lines, "target": target})


@tool
def nikto_scan(target: str, timeout: float = 1800.0) -> str:
    """Run ``nikto`` for legacy web misconfiguration checks."""
    out = scratch_file(".json")
    argv = ["nikto", "-host", target, "-Format", "json", "-output", str(out), "-ask", "no"]
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"target": target})


@tool
def ffuf_fuzz(
    url: str,
    wordlist: str = "/usr/share/wordlists/dirb/common.txt",
    extensions: str = "",
    match_codes: str = "200,204,301,302,307,401,403",
    timeout: float = 900.0,
) -> str:
    """Run ``ffuf`` against a URL with a wordlist.

    ``url`` must contain the ``FUZZ`` marker. Example:
    ``https://target.com/FUZZ``. Writes JSON output for
    ``kg_ingest_ffuf``.
    """
    if "FUZZ" not in url:
        return format_result(
            run_command(["ffuf", "-V"], timeout=5.0),
            extra={"error": "url must contain FUZZ keyword"},
        )
    out = scratch_file(".json")
    argv = [
        "ffuf",
        "-u",
        url,
        "-w",
        wordlist,
        "-mc",
        match_codes,
        "-of",
        "json",
        "-o",
        str(out),
        "-s",
    ]
    if extensions:
        argv.extend(["-e", extensions])
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"url": url})


@tool
def gobuster_dir(
    url: str,
    wordlist: str = "/usr/share/wordlists/dirb/common.txt",
    extensions: str = "",
    threads: int = 30,
    timeout: float = 900.0,
) -> str:
    """Run ``gobuster dir`` for directory brute-force discovery."""
    out = scratch_file(".txt")
    argv = [
        "gobuster",
        "dir",
        "-u",
        url,
        "-w",
        wordlist,
        "-t",
        str(threads),
        "-q",
        "-o",
        str(out),
    ]
    if extensions:
        argv.extend(["-x", extensions])
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"url": url})


@tool
def dirsearch_scan(
    url: str,
    wordlist: str = "",
    extensions: str = "php,html,txt,js",
    timeout: float = 900.0,
) -> str:
    """Run ``dirsearch`` for advanced web path discovery."""
    out = scratch_file(".json")
    argv = ["dirsearch", "-u", url, "-e", extensions, "--format", "json", "-o", str(out), "-q"]
    if wordlist:
        argv.extend(["-w", wordlist])
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"url": url})


@tool
def testssl_scan(target: str, timeout: float = 900.0) -> str:
    """Run ``testssl.sh`` against a host:port and write JSON output.

    Feed the JSON to ``kg_ingest_testssl`` to surface TLS findings as
    vulnerability nodes.
    """
    out = scratch_file(".json")
    argv = ["testssl.sh", "--jsonfile", str(out), "--color", "0", "--quiet", target]
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"target": target})


@tool
def whatweb_scan(target: str, aggression: int = 3, timeout: float = 180.0) -> str:
    """Run ``whatweb`` for CMS / framework fingerprinting."""
    argv = ["whatweb", f"--aggression={aggression}", "--log-json=-", target]
    result = run_command(argv, timeout=timeout)
    return format_result(result, extra={"target": target})


@tool
def wafw00f_detect(target: str, timeout: float = 120.0) -> str:
    """Run ``wafw00f`` to detect a WAF in front of the target."""
    argv = ["wafw00f", "-a", target]
    result = run_command(argv, timeout=timeout)
    return format_result(result, extra={"target": target})


WEB_SCAN_TOOLS = [
    nuclei_scan,
    nikto_scan,
    ffuf_fuzz,
    gobuster_dir,
    dirsearch_scan,
    testssl_scan,
    whatweb_scan,
    wafw00f_detect,
]

__all__ = ["WEB_SCAN_TOOLS"]
