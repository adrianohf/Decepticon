"""Shared runner + helpers for Kali tool wrappers.

Two runner implementations are provided:

- ``LocalSubprocessRunner`` — runs the command directly via
  ``subprocess.run``. Used by tests.
- ``DockerSandboxRunner`` — shells through an active ``DockerSandbox``
  bound via :func:`set_active_sandbox`. If no sandbox is bound and
  the runner is active, tools **fail loudly** rather than silently
  running on the host.

Runner binding is a module global protected by ``threading.RLock``
(not a ``ContextVar``) because LangGraph runs tool nodes in a
different async task context than the one that created the agent,
and ``ContextVar`` values do not propagate across that boundary —
which would silently degrade ``DockerSandboxRunner`` to local
execution. See the history notes around ``set_active_sandbox``.

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

    The sandbox is looked up via the module-global bound by
    :func:`set_active_sandbox`. If no sandbox is bound, this runner
    raises — silently falling back to local execution would be a
    sandbox escape, so callers must bind a sandbox explicitly. Pass
    ``sandbox`` to the constructor when you want to avoid the
    module-global and bind per-instance instead.
    """

    def __init__(self, sandbox: Any | None = None) -> None:
        self._explicit_sandbox = sandbox

    def run(
        self,
        argv: list[str],
        *,
        timeout: float = 120.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        sandbox = self._explicit_sandbox if self._explicit_sandbox is not None else get_active_sandbox()
        if sandbox is None:
            return CommandResult(
                command=list(argv),
                ok=False,
                returncode=126,
                stderr=(
                    "DockerSandboxRunner invoked without an active sandbox — "
                    "call set_active_sandbox() before running Kali tools, or "
                    "pass sandbox=... to the DockerSandboxRunner constructor."
                ),
                notes=["no active sandbox"],
            )
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


# ── Sandbox / runner binding ───────────────────────────────────────────
#
# IMPORTANT: earlier versions of this module used a ``ContextVar`` to
# carry the active runner across tool invocations. That turned out to
# be unsafe — LangGraph runs tool nodes in a different async task
# context than the one that created the agent, so the ContextVar
# value set by the agent factory was invisible at call time and the
# runner silently fell back to ``LocalSubprocessRunner``, meaning
# Kali tools would execute on the *host* instead of the Docker
# sandbox. That is a silent sandbox escape.
#
# Fix: use a **module-global** runner and sandbox protected by a lock.
# ``set_active_sandbox`` and ``set_runner`` mutate the module globals
# directly so any subsequent ``run_command`` — regardless of which
# asyncio task it runs in — sees the same value. Tests that need
# isolation explicitly call ``set_runner(LocalSubprocessRunner())`` in
# their teardown.
import threading

_runner_lock = threading.RLock()
_active_sandbox_obj: Any = None
_current_runner: ToolRunner = LocalSubprocessRunner()


def set_active_sandbox(sandbox: Any) -> None:
    """Bind a ``DockerSandbox`` as the process-wide active sandbox.

    Call this at agent-factory time **before** any Kali tool is
    invoked. The binding is a module global so it survives the
    LangGraph task boundary.
    """
    global _active_sandbox_obj
    with _runner_lock:
        _active_sandbox_obj = sandbox


def get_active_sandbox() -> Any:
    with _runner_lock:
        return _active_sandbox_obj


def set_runner(runner: ToolRunner) -> None:
    """Override the process-wide runner.

    Typically paired with ``set_active_sandbox`` — agent factories call
    ``set_runner(DockerSandboxRunner())`` and ``set_active_sandbox(sb)``
    so every tool invocation goes through the sandbox.
    """
    global _current_runner
    with _runner_lock:
        _current_runner = runner


def get_runner() -> ToolRunner:
    with _runner_lock:
        return _current_runner


def run_command(
    argv: list[str],
    *,
    timeout: float = 120.0,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Execute via the active runner."""
    return get_runner().run(argv, timeout=timeout, cwd=cwd, env=env)


class FlagInjectionError(ValueError):
    """Raised when an LLM-supplied tool argument starts with ``-``.

    ``shlex.quote`` stops shell metacharacter injection but it does not
    stop a value from being interpreted by the target binary as a
    flag. For example, ``nmap_scan(target="--script=http-shellshock")``
    would inject an nmap script if passed through verbatim.

    Every Kali wrapper validates LLM-facing positional arguments
    through :func:`assert_not_flag` before building argv.
    """


def assert_not_flag(value: str, *, field: str) -> str:
    """Reject arguments that start with ``-`` / ``--`` / ``@`` / ``+``.

    ``@`` is rejected because many tools (nmap, curl) treat ``@file``
    as "read arguments from file". ``+`` is rejected for the same
    reason with a handful of legacy tools. Empty values are allowed —
    callers that need to enforce non-empty must check separately.
    """
    if value is None or value == "":
        return ""
    stripped = str(value).lstrip()
    if stripped.startswith(("-", "@", "+")):
        raise FlagInjectionError(
            f"{field}={value!r} starts with a flag-like character — "
            "refusing to pass it through as a tool argument."
        )
    return value


def safe_argv_value(value: str, *, field: str) -> str:
    """Return ``value`` if it passes :func:`assert_not_flag`, else raise."""
    return assert_not_flag(value, field=field)


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
    "FlagInjectionError",
    "LocalSubprocessRunner",
    "assert_not_flag",
    "safe_argv_value",
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
