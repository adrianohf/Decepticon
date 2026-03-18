"""Kali Linux-style bash result renderer."""

import re

from rich.text import Text

from decepticon.ui.cli.console import console

# Kali Linux terminal palette
_BG = "on #1e1e1e"
_GREEN = f"{_BG} bold #5fd700"
_RED_BOLD = f"{_BG} bold #ff5555"
_BLUE = f"{_BG} bold #5f87ff"
_CMD = f"{_BG} bold #ffffff"  # typed command — bright white, bold
_OUTPUT = f"{_BG} #888888"  # stdout — dim gray (clear separation from cmd)
_OUTPUT_ERR = f"{_BG} bold #ff5555"
_OUTPUT_INFO = f"{_BG} #8be9fd"
_INPUT_ARROW = f"{_BG} #555555"
_INPUT_CMD = f"{_BG} bold #e5c07b"

# Pattern to extract [cwd: /path] metadata from sandbox output
_CWD_PATTERN = re.compile(r"\n?\[cwd: (.+?)\]\s*$")


def _extract_cwd(result: str) -> tuple[str, str]:
    """Extract and strip [cwd: /path] metadata from result.

    Returns (cleaned_result, cwd_path).
    """
    m = _CWD_PATTERN.search(result)
    if m:
        return result[: m.start()], m.group(1)
    return result, ""


def render_bash_result(tc: dict, msg, last_bash_session_outputs: dict):
    """Render bash tool result with Kali-like terminal styling."""
    cmd = tc["args"].get("command", "")
    session_id = tc["args"].get("session", "main")
    is_input = tc["args"].get("is_input", False)
    raw_result = str(msg.content).strip()

    # Extract cwd metadata before processing
    clean_result, cwd = _extract_cwd(raw_result)
    clean_result = clean_result.strip()

    # Suppress rendering for empty-command polling that returns status signals
    if not cmd and not is_input and clean_result.startswith(("[RUNNING]", "[IDLE]")):
        return

    out_style = _OUTPUT
    if clean_result.startswith("[ERROR]") or clean_result.startswith("[TIMEOUT]"):
        out_style = _OUTPUT_ERR
    elif clean_result.startswith("[STALLED]"):
        if "Last output:\n" in clean_result:
            parts = clean_result.split("Last output:\n")
            if len(parts) > 1:
                inner = parts[1]
                if "\n\nOptions:" in inner:
                    inner = inner.split("\n\nOptions:")[0]
                clean_result = inner.strip()
    elif clean_result.startswith(("[IDLE]", "[RUNNING]", "[BACKGROUND]")):
        out_style = _OUTPUT_INFO

    # Diff against previous output — only show new lines
    prev_output = last_bash_session_outputs.get(session_id, "")
    display_result = clean_result

    if prev_output and display_result:
        prev_lines = prev_output.split("\n")
        curr_lines = display_result.split("\n")

        overlap = 0
        for i in range(min(len(prev_lines), len(curr_lines))):
            if prev_lines[i] == curr_lines[i]:
                overlap = i + 1
            else:
                break

        if overlap > 0:
            if overlap < len(prev_lines) and overlap < len(curr_lines):
                if curr_lines[overlap].startswith(prev_lines[overlap]):
                    first_new_line_diff = curr_lines[overlap][len(prev_lines[overlap]) :]
                    remaining = curr_lines[overlap + 1 :]
                    curr_lines = [first_new_line_diff] + remaining
                    overlap = 0
            display_result = "\n".join(curr_lines[overlap:])

    if clean_result:
        last_bash_session_outputs[session_id] = clean_result

    console.print()

    if is_input:
        t = Text("  ↳ ", style=_INPUT_ARROW)
        t.append(cmd, style=_INPUT_CMD)
        console.print(t)
    else:
        # Use real cwd from sandbox, fallback to /workspace
        display_cwd = cwd if cwd else "/workspace"

        t1 = Text("┌──(", style=_GREEN)
        t1.append("root㉿sandbox", style=_RED_BOLD)
        t1.append(")-[", style=_GREEN)
        t1.append(display_cwd, style=_BLUE)
        t1.append("]", style=_GREEN)

        t2 = Text("└─# ", style=_GREEN)
        t2.append(cmd, style=_CMD)

        console.print(t1)
        console.print(t2)

    if display_result:
        lines = display_result.split("\n")
        if lines and lines[0].strip() == cmd.strip():
            lines = lines[1:]
        for line in lines:
            if line.strip() or len(lines) > 1:
                console.print(Text(line, style=out_style))

    console.print()
