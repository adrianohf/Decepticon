"""Smoke tests for the Kali tool @tool wrappers.

We swap the runner with a fake that records argv and returns a
canned :class:`CommandResult`. This lets us assert the wrappers build
the right command lines without ever invoking real binaries.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from decepticon.kali_tools import (
    CREDENTIAL_TOOLS,
    EXPLOIT_TOOLS,
    KALI_TOOLS,
    NETWORK_TOOLS,
    RECON_TOOLS,
    WEB_SCAN_TOOLS,
    credential,
    exploit,
    network,
    recon,
    web_scan,
)
from decepticon.kali_tools._common import (
    CommandResult,
    LocalSubprocessRunner,
    set_runner,
)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.next_result: CommandResult | None = None

    def run(self, argv, *, timeout=120.0, cwd=None, env=None):
        self.calls.append(list(argv))
        if self.next_result is not None:
            r = self.next_result
            r.command = list(argv)
            return r
        return CommandResult(command=list(argv), ok=True, returncode=0)


@pytest.fixture(autouse=True)
def fake_runner() -> Iterator[FakeRunner]:
    runner = FakeRunner()
    set_runner(runner)
    yield runner
    set_runner(LocalSubprocessRunner())


def _invoke(tool: Any, **kwargs: Any) -> dict[str, Any]:
    return json.loads(tool.invoke(kwargs))


class TestPackageContents:
    def test_kali_tools_count(self) -> None:
        assert len(KALI_TOOLS) >= 20
        assert all(hasattr(t, "invoke") for t in KALI_TOOLS)

    def test_groups_disjoint(self) -> None:
        all_groups = [
            RECON_TOOLS,
            NETWORK_TOOLS,
            WEB_SCAN_TOOLS,
            EXPLOIT_TOOLS,
            CREDENTIAL_TOOLS,
        ]
        names: list[str] = []
        for grp in all_groups:
            names.extend(t.name for t in grp)
        assert len(names) == len(set(names)), "duplicate tool names across groups"


class TestReconWrappers:
    def test_subfinder_command(self, fake_runner: FakeRunner) -> None:
        _invoke(recon.subfinder_enum, domain="example.com")
        argv = fake_runner.calls[0]
        assert argv[0] == "subfinder"
        assert "-d" in argv and "example.com" in argv
        assert "-o" in argv

    def test_amass_passive_default(self, fake_runner: FakeRunner) -> None:
        _invoke(recon.amass_enum, domain="example.com")
        argv = fake_runner.calls[0]
        assert argv[0] == "amass"
        assert "-passive" in argv

    def test_dnsx_requires_input(self, fake_runner: FakeRunner) -> None:
        out = _invoke(recon.dnsx_resolve)
        assert "error" in out

    def test_dnsx_with_hosts_file(self, fake_runner: FakeRunner) -> None:
        _invoke(recon.dnsx_resolve, hosts_file="/tmp/h.txt")
        # Both --help and the real call get recorded; pick the dnsx one
        dnsx_calls = [c for c in fake_runner.calls if c[0] == "dnsx"]
        assert dnsx_calls
        assert "-l" in dnsx_calls[0]

    def test_httpx_with_targets(self, fake_runner: FakeRunner) -> None:
        _invoke(recon.httpx_probe, targets="https://example.com")
        httpx_calls = [c for c in fake_runner.calls if c[0] == "httpx"]
        assert httpx_calls
        assert "-u" in httpx_calls[0]

    def test_katana_command(self, fake_runner: FakeRunner) -> None:
        _invoke(recon.katana_crawl, url="https://example.com", depth=2)
        argv = fake_runner.calls[0]
        assert argv[0] == "katana"
        assert "-u" in argv
        assert "-d" in argv


class TestNetworkWrappers:
    def test_nmap_command(self, fake_runner: FakeRunner) -> None:
        _invoke(network.nmap_scan, target="192.0.2.1", ports="22,80,443")
        argv = fake_runner.calls[0]
        assert argv[0] == "nmap"
        assert "-Pn" in argv
        assert "-oX" in argv
        assert "192.0.2.1" in argv

    def test_masscan_command(self, fake_runner: FakeRunner) -> None:
        _invoke(network.masscan_scan, target="10.0.0.0/24", rate=2000)
        argv = fake_runner.calls[0]
        assert argv[0] == "masscan"
        assert "--rate" in argv
        assert "2000" in argv

    def test_rustscan_command(self, fake_runner: FakeRunner) -> None:
        _invoke(network.rustscan_scan, target="example.com")
        argv = fake_runner.calls[0]
        assert argv[0] == "rustscan"


class TestWebScanWrappers:
    def test_nuclei_with_severity(self, fake_runner: FakeRunner) -> None:
        _invoke(web_scan.nuclei_scan, target="https://example.com", severity="critical,high")
        argv = fake_runner.calls[0]
        assert argv[0] == "nuclei"
        assert "-severity" in argv

    def test_ffuf_requires_fuzz_marker(self, fake_runner: FakeRunner) -> None:
        out = _invoke(web_scan.ffuf_fuzz, url="https://example.com/no-marker")
        assert "error" in out

    def test_ffuf_with_marker(self, fake_runner: FakeRunner) -> None:
        _invoke(web_scan.ffuf_fuzz, url="https://example.com/FUZZ")
        ffuf_calls = [c for c in fake_runner.calls if c[0] == "ffuf"]
        assert ffuf_calls

    def test_gobuster_command(self, fake_runner: FakeRunner) -> None:
        _invoke(web_scan.gobuster_dir, url="https://example.com")
        argv = fake_runner.calls[0]
        assert argv[0] == "gobuster"
        assert "dir" in argv

    def test_testssl_command(self, fake_runner: FakeRunner) -> None:
        _invoke(web_scan.testssl_scan, target="example.com:443")
        argv = fake_runner.calls[0]
        assert argv[0] == "testssl.sh"

    def test_whatweb_command(self, fake_runner: FakeRunner) -> None:
        _invoke(web_scan.whatweb_scan, target="https://example.com")
        argv = fake_runner.calls[0]
        assert argv[0] == "whatweb"


class TestExploitWrappers:
    def test_sqlmap_batch_default(self, fake_runner: FakeRunner) -> None:
        _invoke(exploit.sqlmap_scan, url="https://example.com/?id=1")
        argv = fake_runner.calls[0]
        assert argv[0] == "sqlmap"
        assert "--batch" in argv
        assert "--level" in argv


class TestCredentialWrappers:
    def test_hydra_command(self, fake_runner: FakeRunner) -> None:
        _invoke(
            credential.hydra_brute,
            target="10.0.0.1",
            service="ssh",
            userlist="/u",
            passlist="/p",
        )
        argv = fake_runner.calls[0]
        assert argv[0] == "hydra"
        assert "ssh" in argv
        assert "10.0.0.1" in argv

    def test_crackmapexec_with_password(self, fake_runner: FakeRunner) -> None:
        _invoke(
            credential.crackmapexec_run,
            protocol="smb",
            target="10.0.0.1",
            username="alice",
            password="hunter2",
        )
        argv = fake_runner.calls[0]
        assert argv[0] == "crackmapexec"
        assert "smb" in argv
        assert "-u" in argv

    def test_crackmapexec_with_hash(self, fake_runner: FakeRunner) -> None:
        _invoke(
            credential.crackmapexec_run,
            protocol="winrm",
            target="10.0.0.2",
            username="bob",
            ntlm_hash="aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0",
        )
        argv = fake_runner.calls[0]
        assert "-H" in argv

    def test_getnpusers_command(self, fake_runner: FakeRunner) -> None:
        _invoke(credential.getnpusers_asrep, domain="CORP", dc_ip="10.0.0.10", username="alice")
        argv = fake_runner.calls[0]
        assert argv[0] == "impacket-GetNPUsers"
        assert "CORP/alice" in argv

    def test_getuserspns_command(self, fake_runner: FakeRunner) -> None:
        _invoke(
            credential.getuserspns_kerberoast,
            domain="CORP",
            username="bob",
            password="secret",
            dc_ip="10.0.0.10",
        )
        argv = fake_runner.calls[0]
        assert argv[0] == "impacket-GetUserSPNs"
        assert "CORP/bob:secret" in argv
