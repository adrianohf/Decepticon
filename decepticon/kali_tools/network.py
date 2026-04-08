"""Network / port-scan tool wrappers — nmap, masscan, rustscan."""

from __future__ import annotations

from langchain_core.tools import tool

from decepticon.kali_tools._common import (
    FlagInjectionError,
    assert_not_flag,
    format_result,
    run_command,
    scratch_file,
)


def _flag_error(tool_name: str, reason: str) -> str:
    import json as _json

    return _json.dumps(
        {"ok": False, "error": f"{tool_name}: {reason}"},
        indent=2,
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
    try:
        assert_not_flag(target, field="target")
        assert_not_flag(ports, field="ports")
        if scripts:
            assert_not_flag(scripts, field="scripts")
    except FlagInjectionError as e:
        return _flag_error("nmap", str(e))
    out = scratch_file(".xml")
    argv = ["nmap", "-Pn", "-n", f"-T{timing}", "-p", ports, "-oX", str(out)]
    if service_version:
        argv.append("-sV")
    if scripts:
        argv.extend(["--script", scripts])
    argv.extend(["--", target])
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
    try:
        assert_not_flag(target, field="target")
        assert_not_flag(ports, field="ports")
    except FlagInjectionError as e:
        return _flag_error("masscan", str(e))
    out = scratch_file(".json")
    argv = [
        "masscan",
        "-p",
        ports,
        "--rate",
        str(rate),
        "-oJ",
        str(out),
        "--",
        target,
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
    try:
        assert_not_flag(target, field="target")
        assert_not_flag(ports, field="ports")
    except FlagInjectionError as e:
        return _flag_error("rustscan", str(e))
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
