"""Tests for the Kali tools runner harness."""

from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.kali_tools._common import (
    CommandResult,
    DockerSandboxRunner,
    LocalSubprocessRunner,
    format_result,
    get_runner,
    run_command,
    set_active_sandbox,
    set_runner,
)


class FakeRunner:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.calls: list[list[str]] = []

    def run(self, argv, *, timeout=120.0, cwd=None, env=None):
        self.calls.append(list(argv))
        return self.result


@pytest.fixture(autouse=True)
def reset_runner():
    yield
    set_runner(LocalSubprocessRunner())
    set_active_sandbox(None)


class TestRunnerSwap:
    def test_get_runner_default(self) -> None:
        # autouse fixture above resets to local
        assert isinstance(get_runner(), LocalSubprocessRunner)

    def test_set_runner_overrides(self) -> None:
        fake = FakeRunner(CommandResult(command=["x"], ok=True, returncode=0))
        set_runner(fake)
        result = run_command(["echo", "hi"])
        assert result.ok
        assert fake.calls == [["echo", "hi"]]


class TestLocalSubprocessRunner:
    def test_runs_real_command(self) -> None:
        result = LocalSubprocessRunner().run(["true"], timeout=5.0)
        assert result.ok
        assert result.returncode == 0

    def test_missing_binary(self) -> None:
        result = LocalSubprocessRunner().run(["this-binary-definitely-not-on-path"], timeout=5.0)
        assert not result.ok
        assert result.returncode == 127
        assert any("not found" in n for n in result.notes)

    def test_timeout(self) -> None:
        result = LocalSubprocessRunner().run(["sleep", "5"], timeout=0.1)
        assert not result.ok
        assert result.returncode == 124
        assert any("timeout" in n for n in result.notes)


class TestDockerSandboxRunner:
    def test_falls_back_when_no_sandbox(self) -> None:
        # No active sandbox → DockerSandboxRunner forwards to local
        runner = DockerSandboxRunner()
        result = runner.run(["true"], timeout=5.0)
        assert result.ok

    def test_uses_sandbox_when_set(self) -> None:
        class StubSandbox:
            def __init__(self) -> None:
                self.last_cmd = ""

            def execute(self, cmd: str, timeout: int = 0) -> object:
                self.last_cmd = cmd

                class _R:
                    stdout = "fake-output"
                    stderr = ""
                    returncode = 0

                return _R()

        stub = StubSandbox()
        set_active_sandbox(stub)
        result = DockerSandboxRunner().run(["echo", "hi there"], timeout=5.0)
        assert result.ok
        assert "echo" in stub.last_cmd
        assert "hi there" in stub.last_cmd
        assert result.stdout == "fake-output"


class TestFormatResult:
    def test_envelope_shape(self) -> None:
        result = CommandResult(command=["nmap", "-V"], ok=True, returncode=0, stdout="x")
        envelope = format_result(result, extra={"target": "1.2.3.4"})
        assert "1.2.3.4" in envelope
        assert "nmap" in envelope
        assert '"ok": true' in envelope


class TestScratchFile:
    def test_unique_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_KALI_SCRATCH", str(tmp_path))
        # Re-import to pick up env var
        import importlib

        import decepticon.kali_tools._common as common

        importlib.reload(common)
        a = common.scratch_file(".txt")
        b = common.scratch_file(".txt")
        assert a != b
        assert a.suffix == ".txt"
