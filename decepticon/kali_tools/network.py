"""Network / port-scan tool wrappers — nmap, masscan, rustscan."""

from __future__ import annotations

from langchain_core.tools import tool

from decepticon.kali_tools._common import (
    format_result,
    run_command,
    scratch_file,
)


@tool
def nmap_scan(
    target: str,
    ports: str = "1-10000",
    service_version: bool = True,
    scripts: str = "default",
    timing: int = 4,
    timeout: float = 1800.0,
) -> str:
    """Run ``nmap`` against a target and write XML output.

    Defaults to the common "-sV -sC" combo with ``-T4`` timing and the
    top 10,000 ports. Returns the XML path so downstream
    ``kg_ingest_nmap_xml`` can absorb the findings directly.
    """
    out = scratch_file(".xml")
    argv = ["nmap", "-Pn", "-n", f"-T{timing}", "-p", ports, "-oX", str(out)]
    if service_version:
        argv.append("-sV")
    if scripts:
        argv.extend(["--script", scripts])
    argv.append(target)
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"target": target, "ports": ports})


@tool
def masscan_scan(
    target: str,
    ports: str = "0-65535",
    rate: int = 5000,
    timeout: float = 1800.0,
) -> str:
    """Run ``masscan`` for internet-scale fast port discovery.

    Output is JSON. Feed the path to ``kg_ingest_masscan`` to populate
    host/service nodes for follow-up nmap verification.
    """
    out = scratch_file(".json")
    argv = [
        "masscan",
        target,
        "-p",
        ports,
        "--rate",
        str(rate),
        "-oJ",
        str(out),
    ]
    result = run_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"target": target, "ports": ports, "rate": rate})


@tool
def rustscan_scan(
    target: str,
    ports: str = "1-65535",
    batch_size: int = 5000,
    timeout: float = 600.0,
) -> str:
    """Run ``rustscan`` (fast port scanner that hands off to nmap).

    Returns raw stdout — rustscan doesn't emit structured output by
    default, but the agent can parse the ``[tcp]`` lines to seed a
    targeted nmap follow-up.
    """
    argv = [
        "rustscan",
        "-a",
        target,
        "-r",
        ports,
        "-b",
        str(batch_size),
        "--accessible",
        "--no-config",
    ]
    result = run_command(argv, timeout=timeout)
    return format_result(result, extra={"target": target, "ports": ports})


NETWORK_TOOLS = [
    nmap_scan,
    masscan_scan,
    rustscan_scan,
]

__all__ = ["NETWORK_TOOLS"]
