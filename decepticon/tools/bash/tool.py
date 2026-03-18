"""Bash tool for the Decepticon agent.

Thin wrapper around DockerSandbox.execute_tmux(). All tmux session
management and PS1 polling logic lives in decepticon/backends/docker_sandbox.py.

The sandbox instance is injected at agent startup via set_sandbox().

Context engineering: tool output offloading
-------------------------------------------
When tool output exceeds OFFLOAD_THRESHOLD, the full output is automatically
saved to /workspace/.scratch/<session>_<timestamp>.txt inside the sandbox,
and only a compact summary + file reference is returned to the agent context.
This implements the "filesystem as scratch pad" pattern from filesystem-context,
dramatically reducing context consumption from verbose scan outputs.
"""

from __future__ import annotations

import hashlib
import time

from langchain_core.tools import tool

from decepticon.backends.docker_sandbox import DockerSandbox

_sandbox: DockerSandbox | None = None

# Tool output offloading threshold (chars).
# Outputs exceeding this are saved to file and replaced with a summary.
OFFLOAD_THRESHOLD = 15_000


def _sanitize_output(text: str) -> str:
    """Remove surrogate characters that break UTF-8 encoding.

    Tmux capture-pane and docker exec can produce strings with surrogate
    code points (U+D800–U+DFFF) that are invalid in strict UTF-8. When
    LangChain serializes these to JSON for the LLM API call, encoding
    fails with 'surrogates not allowed'. Re-encode with surrogateescape
    then decode back with replace to swap them for U+FFFD.
    """
    return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


def set_sandbox(sandbox: DockerSandbox) -> None:
    """Inject the shared DockerSandbox instance (called from recon.py)."""
    global _sandbox
    _sandbox = sandbox


def get_sandbox() -> DockerSandbox | None:
    """Return the current DockerSandbox instance (for wiring progress callbacks)."""
    return _sandbox


def _offload_large_output(output: str, command: str, session: str) -> str:
    """Save large output to scratch file in sandbox, return compact reference.

    Implements the filesystem-context "scratch pad" pattern:
    - Write full output to /workspace/.scratch/ for later retrieval
    - Return summary + file path reference to keep context lean
    - Agent can use read_file or grep to access specific parts later
    """
    assert _sandbox is not None

    # Generate unique filename
    ts = int(time.time())
    cmd_hash = hashlib.md5(command.encode()).hexdigest()[:6]
    filename = f"/workspace/.scratch/{session}_{ts}_{cmd_hash}.txt"

    # Ensure scratch directory exists and write file
    _sandbox.execute("mkdir -p /workspace/.scratch")
    _sandbox.execute(f"cat > {filename} << 'DCPTN_EOF'\n{output}\nDCPTN_EOF")

    # Build compact summary
    line_count = output.count("\n") + 1
    char_count = len(output)
    preview_lines = output[:500].strip()
    tail_lines = output[-300:].strip()

    return (
        f"{preview_lines}\n\n"
        f"[... {line_count} lines / {char_count} chars — full output saved to {filename} ...]\n\n"
        f"...{tail_lines}\n\n"
        f"[Full output: {filename} — use read_file or grep to search specific content]"
    )


@tool
def bash(
    command: str = "",
    is_input: bool = False,
    session: str = "main",
    timeout: int = 120,
    background: bool = False,
) -> str:
    """Execute a bash command inside the isolated Docker sandbox (Kali Linux).

    WHAT: Runs shell commands in a persistent tmux session inside the Docker container.
    Each session maintains state (cwd, env vars, background processes) across calls.
    Long-running commands auto-wait at the tool level until completion or timeout —
    no need to poll with empty commands.

    WHEN TO USE:
    - Running recon tools: nmap, dig, whois, subfinder, curl, netcat
    - File operations inside sandbox: cat, ls, grep on /workspace files
    - Installing missing packages: apt-get install -y <pkg>
    - Checking a parallel session: bash(command="", session="scan-1")

    RETURNS:
    - Command output (stdout). Exit code appended on failure.
    - For large outputs (>15K chars): output is auto-saved to /workspace/.scratch/ and a
      summary with file path is returned. Use read_file or grep to access full content.
    - [BACKGROUND]: Command started in session. Do NOT check immediately — do other work first.
    - [TIMEOUT]: Session is now OCCUPIED. Use a DIFFERENT session for new commands.
    - [IDLE]: Session ready, no running process (when checking a session with empty command).
    - [RUNNING]: Session has active output (when checking a session with empty command).

    ERROR RECOVERY:
    - [TIMEOUT] → Session occupied. Use a different session name for new commands.
      Check the timed-out session later: bash(command="", session="<same>")
    - Permission denied → Try with sudo or check file path
    - Command not found → Install: bash(command="apt-get update && apt-get install -y <pkg>")

    Args:
        command: Shell command to execute. Leave empty to read current screen output of the session.
        is_input: ONLY set True when a PREVIOUS command in this session is waiting for input.
            Use for: interactive responses ('y', 'n'), passwords, or control signals ('C-c', 'C-z', 'C-d').
            NEVER set True when starting a new command.
        session: Tmux session name for parallel execution. Example: session="scan-1" and session="scan-2"
            run two scans concurrently. Default "main" for sequential work.
        timeout: Max seconds to wait for command completion (default 120). Increase for long scans.
        background: Set True to start a long-running command without waiting for completion.
            The command runs in the named session. Check results later with bash(session="<name>").
            ALWAYS use a dedicated session name (not "main") with background=True.
            Example: bash(command="nmap -sV target", session="nmap", background=True)
    """
    if _sandbox is None:
        raise RuntimeError("DockerSandbox not initialized. Call set_sandbox() first.")

    # Background mode: send command and return immediately
    if background and command:
        _sandbox.start_background(command=command, session=session)
        return (
            f"[BACKGROUND] Command started in session '{session}'.\n"
            f"Do NOT check this session or sleep-wait. Instead, do productive work NOW:\n"
            f"  - Run quick commands (curl, dig, whois) on 'main' session\n"
            f"  - Enumerate services on already-discovered ports\n"
            f"  - Read skill files or analyze existing findings\n"
            f'Check later: bash(command="", session="{session}")'
        )

    result = _sandbox.execute_tmux(
        command=command,
        session=session,
        timeout=timeout,
        is_input=is_input,
    )

    # Sanitize surrogates before any downstream UTF-8 encoding
    result = _sanitize_output(result)

    # Auto-offload large outputs to scratch files (filesystem-context pattern)
    if len(result) > OFFLOAD_THRESHOLD and not result.startswith("["):
        return _offload_large_output(result, command, session)

    return result
