"""Shared runner + helpers for Kali tool wrappers.

Two runner implementations are provided:

- ``LocalSubprocessRunner`` — runs the command directly via
  ``subprocess.run``. Used by tests and by agents that aren't wired
  through a Docker sandbox.
- ``DockerSandboxRunner`` — shells through an existing
  ``DockerSandbox`` instance. Chosen automatically when the sandbox
  context variable is set (see ``set_active_sandbox``).

The default runner is resolved lazily via ``get_runner()`` so tests
can swap implementations with ``set_runner()`` without import-time
ordering hazards.

Result shape is deliberately minimal:

    CommandResult(
        ok=True/False,
        returncode=0,
        stdout="...",
        stderr="...",
        duration_s=0.123,
        command=["nmap", "-sV", "target"],
        output_path="/workspace/.scratch/abcd.json" | "",
    )

``output_path`` is set whenever the tool writes a structured output
file (nmap XML, nuclei JSONL, etc.) — downstream kg_ingest_* tools
read from that path directly.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from decepticon.core.logging import get_logger

log = get_logger("kali_tools")

SCRATCH_DIR = Path(os.environ.get("DECEPTICON_KALI_SCRATCH", "/tmp/decepticon-kali"))


@dataclass
class CommandResult:
    """Captured output of a tool invocation."""

    command: list[str]
    ok: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    output_path: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": " ".join(shlex.quote(c) for c in self.command),
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": _truncate(self.stdout),
            "stderr": _truncate(self.stderr),
            "duration_s": round(self.duration_s, 3),
            "output_path": self.output_path,
            "notes": list(self.notes),
        }


def _truncate(text: str, *, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    head = text[: int(limit * 0.6)]
    tail = text[-int(limit * 0.4) :]
    return f"{head}\n…[truncated {len(text) - limit} chars]…\n{tail}"


class ToolRunner(Protocol):
    """Execution backend for Kali tool commands."""

    def run(
        self,
        argv: list[str],
        *,
        timeout: float = 120.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult: ...


class LocalSubprocessRunner:
    """Direct ``subprocess.run`` — no sandbox."""

    def run(
        self,
        argv: list[str],
        *,
        timeout: float = 120.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env={**os.environ, **(env or {})} if env else None,
                check=False,
            )
            duration = time.monotonic() - started
            return CommandResult(
                command=argv,
                ok=completed.returncode == 0,
                returncode=completed.returncode,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                duration_s=duration,
            )
        except FileNotFoundError as e:
            return CommandResult(
                command=argv,
                ok=False,
                returncode=127,
                stderr=str(e),
                duration_s=time.monotonic() - started,
                notes=[f"binary not found: {argv[0]}"],
            )
        except subprocess.TimeoutExpired as e:
            return CommandResult(
                command=argv,
                ok=False,
                returncode=124,
                stdout=(e.stdout.decode("utf-8", "replace") if e.stdout else ""),
                stderr=(e.stderr.decode("utf-8", "replace") if e.stderr else ""),
                duration_s=timeout,
                notes=[f"timeout after {timeout}s"],
            )


class DockerSandboxRunner:
    """Run the tool inside an active :class:`DockerSandbox`.

    The sandbox is looked up via ``_active_sandbox`` which callers set
    with :func:`set_active_sandbox`. If no sandbox is bound, this
    runner falls back to ``LocalSubprocessRunner``.
    """

    def run(
        self,
        argv: list[str],
        *,
        timeout: float = 120.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        sandbox = _active_sandbox.get()
        if sandbox is None:
            return LocalSubprocessRunner().run(argv, timeout=timeout, cwd=cwd, env=env)
        started = time.monotonic()
        cmd = " ".join(shlex.quote(c) for c in argv)
        if cwd:
            cmd = f"cd {shlex.quote(cwd)} && {cmd}"
        if env:
            prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
            cmd = f"{prefix} {cmd}"
        try:
            result = sandbox.execute(cmd, timeout=int(timeout))
        except Exception as e:  # pragma: no cover — defensive
            log.warning("sandbox execute failed for %s: %s", argv[0], e)
            return LocalSubprocessRunner().run(argv, timeout=timeout, cwd=cwd, env=env)
        duration = time.monotonic() - started
        stdout = getattr(result, "stdout", None) or getattr(result, "output", "") or ""
        rc = getattr(result, "returncode", getattr(result, "exit_code", 0)) or 0
        return CommandResult(
            command=argv,
            ok=rc == 0,
            returncode=int(rc),
            stdout=str(stdout),
            stderr=str(getattr(result, "stderr", "")),
            duration_s=duration,
        )


_active_sandbox: ContextVar[Any] = ContextVar("decepticon_kali_sandbox", default=None)
_runner: ContextVar[ToolRunner] = ContextVar(
    "decepticon_kali_runner", default=LocalSubprocessRunner()
)


def set_active_sandbox(sandbox: Any) -> None:
    """Bind a ``DockerSandbox`` to the current context.

    Wrap the call to ``DockerSandboxRunner`` users via ``set_runner``
    if you want every subsequent tool invocation to flow through the
    sandbox.
    """
    _active_sandbox.set(sandbox)


def get_active_sandbox() -> Any:
    return _active_sandbox.get()


def set_runner(runner: ToolRunner) -> None:
    """Override the runner for the current context (tests)."""
    _runner.set(runner)


def get_runner() -> ToolRunner:
    return _runner.get()


def run_command(
    argv: list[str],
    *,
    timeout: float = 120.0,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Execute via the active runner."""
    return get_runner().run(argv, timeout=timeout, cwd=cwd, env=env)


def ensure_scratch() -> Path:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    return SCRATCH_DIR


def scratch_file(suffix: str = ".txt") -> Path:
    ensure_scratch()
    return SCRATCH_DIR / f"{uuid.uuid4().hex}{suffix}"


def format_result(
    result: CommandResult,
    *,
    extra: dict[str, Any] | None = None,
) -> str:
    """Standard JSON envelope used by every @tool wrapper."""
    payload: dict[str, Any] = result.to_dict()
    if extra:
        payload.update(extra)
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


__all__ = [
    "CommandResult",
    "DockerSandboxRunner",
    "LocalSubprocessRunner",
    "SCRATCH_DIR",
    "ToolRunner",
    "ensure_scratch",
    "format_result",
    "get_active_sandbox",
    "get_runner",
    "run_command",
    "scratch_file",
    "set_active_sandbox",
    "set_runner",
]
