"""Docker sandbox backend for deepagents.

Implements BaseSandbox using the Docker CLI, with tmux-based execution
for persistent, interactive shell sessions (used by the bash tool).

Architecture:
    DockerSandbox.execute()       → simple docker exec (used by BaseSandbox
                                    file ops: ls, read, write, edit, grep, glob)
    DockerSandbox.execute_tmux()  → tmux session-based (used by bash tool)
                                    supports: session persistence, stalled
                                    detection, interactive input
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Callable

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

log = logging.getLogger("decepticon.backends.docker_sandbox")

# ─── Constants (transplanted from tools/bash/tool.py) ────────────────────

PS1_PATTERN = re.compile(r"\[DCPTN:(\d+):(.+?)\]")
POLL_INTERVAL = 0.5  # seconds between capture-pane polls
NO_CHANGE_TIMEOUT = 10.0  # seconds of silence before declaring STALLED
MAX_OUTPUT_CHARS = 30_000


# ─── TmuxSessionManager ───────────────────────────────────────────────────


class TmuxSessionManager:
    """Manages a single named tmux session inside the Docker container.

    Transplanted from tools/bash/tool.py; docker exec calls now go directly
    through subprocess instead of the old run_in_sandbox() helper.
    """

    _initialized: set[str] = set()

    def __init__(self, session: str, container_name: str) -> None:
        self.session = session
        self._container = container_name

    # ── docker / tmux helpers ──

    def _docker_tmux(self, args: list[str], timeout: int = 10) -> str:
        """Run a tmux subcommand inside the container."""
        result = subprocess.run(
            ["docker", "exec", self._container, "tmux"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout

    def _send(self, text: str, enter: bool = True) -> None:
        """Send keystrokes using -l (literal) to prevent tmux escaping bugs."""
        self._docker_tmux(["send-keys", "-t", self.session, "-l", text])
        if enter:
            self._docker_tmux(["send-keys", "-t", self.session, "Enter"])

    def _clear_screen(self) -> None:
        self._docker_tmux(["send-keys", "-t", self.session, "C-l"])
        time.sleep(0.1)
        self._docker_tmux(["clear-history", "-t", self.session])

    def _capture(self) -> str:
        return self._docker_tmux(
            [
                "capture-pane",
                "-J",
                "-p",
                "-S",
                "-",
                "-E",
                "-",
                "-t",
                self.session,
            ]
        )

    # ── session lifecycle ──

    def initialize(self) -> None:
        """Create session if needed and inject PS1 marker (once per session)."""
        if self.session in TmuxSessionManager._initialized:
            return

        session_exists = False
        try:
            self._docker_tmux(["has-session", "-t", self.session], timeout=5)
            session_exists = True
        except RuntimeError:
            session_exists = False

        if not session_exists:
            log.info("Creating tmux session: %s", self.session)
            try:
                self._docker_tmux(["new-session", "-d", "-s", self.session])
            except RuntimeError as e:
                # "duplicate session" — has-session check was stale; session exists
                if "duplicate session" not in str(e):
                    raise
                log.debug("Session %s already exists (race), reusing", self.session)
            time.sleep(0.3)

        # Inject PS1 marker + disable PS2 + clear screen
        ps1_cmd = "export PROMPT_COMMAND='export PS1=\"[DCPTN:$?:$PWD] \"'; export PS2=''; clear"
        self._send(ps1_cmd)
        time.sleep(0.5)
        self._clear_screen()
        time.sleep(0.2)

        if not session_exists:
            log_path = f"/tmp/.dcptn_log_{self.session}"
            try:
                self._docker_tmux(
                    [
                        "pipe-pane",
                        "-t",
                        self.session,
                        "-o",
                        f"cat >> {log_path}",
                    ]
                )
            except Exception:
                pass  # pipe-pane is optional

        TmuxSessionManager._initialized.add(self.session)

    # ── execution ──

    def execute(
        self,
        command: str,
        is_input: bool,
        timeout: int,
        progress_callback: Callable[[str, str, str], None] | None = None,
    ) -> str:
        """Send a command/input and poll for PS1 completion marker.

        Instead of returning [STALLED] after NO_CHANGE_TIMEOUT, the loop
        continues polling internally until PS1 appears or *timeout* is
        reached. Progress is communicated via *progress_callback* (UI
        only — never enters the LLM context).
        """
        if not is_input:
            self.initialize()

        try:
            baseline = self._capture()
        except RuntimeError as e:
            return f"[ERROR] Sandbox error: {e}"

        initial_count = len(PS1_PATTERN.findall(baseline))

        if command:
            if is_input:
                if command in ("C-c", "C-z", "C-d"):
                    self._docker_tmux(["send-keys", "-t", self.session, command])
                else:
                    self._send(command, enter=True)
            else:
                self._send(command, enter=True)

        start = time.time()
        last_change = start
        last_content = baseline
        stall_notified = False

        while time.time() - start < timeout:
            time.sleep(POLL_INTERVAL)
            try:
                screen = self._capture()
            except RuntimeError:
                continue

            if screen != last_content:
                last_change = time.time()
                last_content = screen
                if stall_notified:
                    stall_notified = False
                    if progress_callback:
                        progress_callback("resumed", self.session, "")

            current_count = len(PS1_PATTERN.findall(screen))

            if current_count > initial_count:
                output, exit_code, cwd = _extract_output(screen, command, initial_count)
                log.info("Command completed: exit=%s cwd=%s [%s]", exit_code, cwd, command[:50])
                self._clear_screen()
                result = _truncate(output).strip()
                if not result:
                    result = f"[Command completed with no output. Exit code: {exit_code}]"
                elif exit_code != 0:
                    result += f"\n[Command failed with exit code: {exit_code}]"
                if cwd:
                    result += f"\n[cwd: {cwd}]"
                return result

            # Stall detected — notify UI but keep polling (no return)
            if not stall_notified and time.time() - last_change >= NO_CHANGE_TIMEOUT:
                stall_notified = True
                if progress_callback:
                    recent = _recent_output(screen)
                    progress_callback("stalled", self.session, recent)
                log.debug(
                    "Stall detected in session %s, continuing to wait (timeout=%ds)",
                    self.session,
                    timeout,
                )

        return (
            f"[TIMEOUT] Command exceeded {timeout}s limit.\n"
            f"Session '{self.session}' is now OCCUPIED — do NOT send new commands to it.\n"
            f"Continue other work using a DIFFERENT session name.\n"
            f'Check this session later: bash(command="", session="{self.session}")'
        )

    def read_screen(self) -> str:
        """Read current screen without sending any command."""
        self.initialize()
        screen = self._capture()
        matches = list(PS1_PATTERN.finditer(screen))
        if matches:
            last = matches[-1]
            exit_code = int(last.group(1))
            cwd = last.group(2)
            recent = screen[last.end() :].strip()
            if recent:
                return f"[RUNNING] cwd={cwd}\n{_truncate(recent)}"
            return f"[IDLE] exit_code={exit_code} cwd={cwd}\nSession is ready for commands."
        return f"[UNKNOWN]\n{screen[-2000:]}"


# ─── Output helpers (transplanted from tools/bash/tool.py) ───────────────


def _extract_output(screen: str, command: str, initial_count: int) -> tuple[str, int, str]:
    matches = list(PS1_PATTERN.finditer(screen))
    if not matches:
        return screen, -1, ""
    last = matches[-1]
    exit_code = int(last.group(1))
    cwd = last.group(2)
    if len(matches) >= 2:
        raw = screen[matches[-2].end() : last.start()]
    else:
        raw = screen[: last.start()]
    lines = raw.strip().split("\n")
    if lines and command and lines[0].strip().endswith(command.strip()):
        lines = lines[1:]
    return "\n".join(lines).strip(), exit_code, cwd


def _recent_output(screen: str) -> str:
    matches = list(PS1_PATTERN.finditer(screen))
    if matches:
        return screen[matches[-1].end() :].strip()
    return screen[-3000:].strip()


def _truncate(text: str) -> str:
    """Truncate large outputs preserving head + tail for context efficiency.

    Observation masking: large tool outputs are the #1 context consumer.
    Keep the first and last portions (highest signal) and summarize the middle.
    """
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    # Asymmetric split: more head (often contains headers/structure) than tail
    head_chars = int(MAX_OUTPUT_CHARS * 0.6)
    tail_chars = MAX_OUTPUT_CHARS - head_chars
    mid_text = text[head_chars:-tail_chars]
    mid_lines = mid_text.count("\n")
    mid_chars = len(mid_text)
    return (
        f"{text[:head_chars]}\n\n"
        f"[... {mid_lines} lines / {mid_chars} chars truncated — "
        f"save full output to file with -oN or redirect (> /workspace/output.txt) "
        f"to preserve complete results ...]\n\n"
        f"{text[-tail_chars:]}"
    )


# ─── DockerSandbox ────────────────────────────────────────────────────────


class DockerSandbox(BaseSandbox):
    """deepagents BaseSandbox backed by a running Docker container.

    File operations (ls, read, write, edit, grep, glob) are handled by
    BaseSandbox, which delegates them to execute() — simple, non-interactive
    docker exec calls sufficient for atomic file ops.

    The bash tool uses execute_tmux() for persistent tmux sessions that
    support interactive input and stalled-process detection.
    """

    def __init__(
        self,
        container_name: str = "decepticon-sandbox",
        default_timeout: int = 120,
    ) -> None:
        self._container_name = container_name
        self._default_timeout = default_timeout
        self._managers: dict[str, TmuxSessionManager] = {}
        self._progress_callback: Callable[[str, str, str], None] | None = None

    def set_progress_callback(self, cb: Callable[[str, str, str], None]) -> None:
        """Set a UI callback for long-running command progress notifications."""
        self._progress_callback = cb

    def _get_manager(self, session: str) -> TmuxSessionManager:
        if session not in self._managers:
            self._managers[session] = TmuxSessionManager(session, self._container_name)
        return self._managers[session]

    # ── BaseSandbox abstract methods ──────────────────────────────────────

    @property
    def id(self) -> str:
        return self._container_name

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Simple docker exec — used by BaseSandbox for file operations."""
        effective = timeout if timeout is not None else self._default_timeout
        try:
            result = subprocess.run(
                ["docker", "exec", self._container_name, "sh", "-c", command],
                capture_output=True,
                text=True,
                timeout=effective,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout
            if result.stderr and result.stderr.strip():
                output += f"\n<stderr>{result.stderr.strip()}</stderr>"
            return ExecuteResponse(
                output=output,
                exit_code=result.returncode,
                truncated=False,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Command timed out after {effective}s",
                exit_code=124,
                truncated=False,
            )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                result = subprocess.run(
                    ["docker", "cp", tmp_path, f"{self._container_name}:{path}"],
                    capture_output=True,
                )
                error = None if result.returncode == 0 else "file_not_found"
            finally:
                import os

                os.unlink(tmp_path)
            responses.append(FileUploadResponse(path=path, error=error))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            result = subprocess.run(
                ["docker", "cp", f"{self._container_name}:{path}", "-"],
                capture_output=True,
            )
            if result.returncode != 0:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
                continue
            try:
                with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
                    member = tar.getmembers()[0]
                    f = tar.extractfile(member)
                    file_bytes = f.read() if f else b""
                responses.append(FileDownloadResponse(path=path, content=file_bytes, error=None))
            except Exception:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
        return responses

    # ── Tmux execution (for bash tool) ───────────────────────────────────

    def execute_tmux(
        self,
        command: str = "",
        session: str = "main",
        timeout: int | None = None,
        is_input: bool = False,
    ) -> str:
        """Tmux-based execution with session persistence and interactive support.

        Used exclusively by the bash tool. Supports:
        - Named sessions for parallel command execution
        - Interactive input (y/n, passwords, C-c / C-z / C-d)
        - Stalled-process detection (10s no-change → callback notification)
        - Output truncation for large outputs
        """
        effective = timeout if timeout is not None else self._default_timeout
        mgr = self._get_manager(session)

        if not command and not is_input:
            return mgr.read_screen()

        return mgr.execute(
            command,
            is_input=is_input,
            timeout=effective,
            progress_callback=self._progress_callback,
        )

    def start_background(self, command: str, session: str = "main") -> None:
        """Send a command to a tmux session without waiting for completion.

        The command runs in the named session and can be checked later via
        execute_tmux(command="", session=...) or read_screen().
        """
        mgr = self._get_manager(session)
        mgr.initialize()
        mgr._send(command, enter=True)


# ─── Pre-flight check ────────────────────────────────────────────────────


def check_sandbox_running(container_name: str = "decepticon-sandbox") -> bool:
    """Check if the Docker sandbox container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False
