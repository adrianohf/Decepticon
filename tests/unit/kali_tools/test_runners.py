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

    @pytest.mark.asyncio
    async def test_arun_real_command(self) -> None:
        result = await LocalSubprocessRunner().arun(["true"], timeout=5.0)
        assert result.ok
        assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_arun_missing_binary(self) -> None:
        result = await LocalSubprocessRunner().arun(
            ["this-binary-definitely-not-on-path"], timeout=5.0
        )
        assert not result.ok
        assert result.returncode == 127

    @pytest.mark.asyncio
    async def test_arun_timeout(self) -> None:
        result = await LocalSubprocessRunner().arun(["sleep", "5"], timeout=0.1)
        assert not result.ok
        assert result.returncode == 124

    @pytest.mark.asyncio
    async def test_arun_captures_stdout(self) -> None:
        result = await LocalSubprocessRunner().arun(["sh", "-c", "printf hello"], timeout=5.0)
        assert result.ok
        assert result.stdout == "hello"


class TestDockerSandboxRunner:
    def test_fails_loudly_when_no_sandbox(self) -> None:
        # Regression guard: silent fallback to local is a sandbox escape.
        # Without an active sandbox, DockerSandboxRunner must return a
        # non-ok result with a clear error instead of running on host.
        set_active_sandbox(None)
        runner = DockerSandboxRunner()
        result = runner.run(["true"], timeout=5.0)
        assert not result.ok
        assert result.returncode == 126
        assert "no active sandbox" in " ".join(result.notes)

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

    @pytest.mark.asyncio
    async def test_arun_uses_async_sandbox_execute(self) -> None:
        class StubSandbox:
            def __init__(self) -> None:
                self.last_cmd = ""
                self.via_async = False

            async def aexecute(self, cmd: str, timeout: int = 0) -> object:
                self.last_cmd = cmd
                self.via_async = True

                class _R:
                    stdout = "async-output"
                    stderr = ""
                    returncode = 0

                return _R()

            def execute(self, cmd: str, timeout: int = 0) -> object:
                raise AssertionError("sync execute should not be called")

        stub = StubSandbox()
        set_active_sandbox(stub)
        result = await DockerSandboxRunner().arun(["echo", "hello"], timeout=5.0)
        assert result.ok
        assert stub.via_async
        assert result.stdout == "async-output"

    @pytest.mark.asyncio
    async def test_arun_wraps_sync_execute_in_thread(self) -> None:
        class StubSandbox:
            def __init__(self) -> None:
                self.last_cmd = ""

            def execute(self, cmd: str, timeout: int = 0) -> object:
                self.last_cmd = cmd

                class _R:
                    stdout = "sync-output"
                    stderr = ""
                    returncode = 0

                return _R()

        stub = StubSandbox()
        set_active_sandbox(stub)
        result = await DockerSandboxRunner().arun(["echo", "hello"], timeout=5.0)
        assert result.ok
        assert result.stdout == "sync-output"
        assert "echo" in stub.last_cmd

    @pytest.mark.asyncio
    async def test_arun_no_sandbox_returns_error(self) -> None:
        set_active_sandbox(None)
        result = await DockerSandboxRunner().arun(["true"], timeout=5.0)
        assert not result.ok
        assert result.returncode == 126

    def test_explicit_sandbox_overrides_module_global(self) -> None:
        class StubSandbox:
            def __init__(self, tag: str) -> None:
                self.tag = tag
                self.last_cmd = ""

            def execute(self, cmd: str, timeout: int = 0) -> object:
                self.last_cmd = f"{self.tag}::{cmd}"

                class _R:
                    stdout = ""
                    stderr = ""
                    returncode = 0

                return _R()

        global_stub = StubSandbox("GLOBAL")
        explicit_stub = StubSandbox("EXPLICIT")
        set_active_sandbox(global_stub)
        runner = DockerSandboxRunner(sandbox=explicit_stub)
        runner.run(["echo", "x"], timeout=5.0)
        assert explicit_stub.last_cmd.startswith("EXPLICIT")
        assert global_stub.last_cmd == ""


class TestFormatResult:
    def test_envelope_shape(self) -> None:
        result = CommandResult(command=["nmap", "-V"], ok=True, returncode=0, stdout="x")
        envelope = format_result(result, extra={"target": "1.2.3.4"})
        assert "1.2.3.4" in envelope
        assert "nmap" in envelope
        assert '"ok": true' in envelope


class TestScratchFile:
    def test_unique_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Patch the module-level SCRATCH_DIR directly. We must NOT
        # ``importlib.reload(common)`` here — a reload rebuilds
        # ``FlagInjectionError`` as a new class, which would break the
        # ``except FlagInjectionError`` handlers that were bound to
        # the pre-reload class object when the tool modules were
        # imported.
        import decepticon.kali_tools._common as common

        monkeypatch.setattr(common, "SCRATCH_DIR", tmp_path)
        a = common.scratch_file(".txt")
        b = common.scratch_file(".txt")
        assert a != b
        assert a.suffix == ".txt"
        assert a.parent == tmp_path
