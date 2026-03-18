"""CLIRenderer — Rich-based UIRenderer implementation."""

from pathlib import PurePosixPath

from decepticon.core.streaming import UIRenderer
from decepticon.ui.cli.console import console
from decepticon.ui.cli.renderers import (
    display_ai_message,
    display_tool_call,
    display_tool_result,
    render_bash_result,
)


def _is_skill_load(tool_name: str, tool_args: dict) -> str | None:
    """Return skill name if this is a skill file read, else None."""
    if tool_name != "read_file":
        return None
    path = tool_args.get("file_path", "")
    if not path.startswith("/skills/"):
        return None
    # /skills/recon/passive-recon/SKILL.md → passive-recon
    # /skills/recon/passive-recon/references/dns-techniques.md → passive-recon/dns-techniques
    p = PurePosixPath(path)
    parts = p.parts  # ('/', 'skills', 'recon', 'passive-recon', 'SKILL.md')
    if len(parts) < 4:
        return None
    skill_name = parts[3]  # e.g. "passive-recon"
    if p.name == "SKILL.md":
        return skill_name
    # Reference file: include filename without extension
    return f"{skill_name}/{p.stem}"


class CLIRenderer(UIRenderer):
    """Rich terminal renderer for agent streaming events.

    Handles both top-level agent events and sub-agent events.
    Sub-agent events are emitted by StreamingRunnable when the Decepticon
    orchestrator delegates work via task(). The `task` tool call/result
    are suppressed since the sub-agent's detailed activity is already shown.
    """

    def __init__(self):
        self._last_bash_session_outputs: dict[str, str] = {}
        self._subagent_bash_outputs: dict[str, str] = {}
        self._active_agent: str = ""

    def set_active_agent(self, name: str) -> None:
        """Set the active agent name for message labeling."""
        self._active_agent = name

    # ── Top-level agent events ────────────────────────────────────────

    def on_tool_call(self, tool_name: str, tool_args: dict) -> None:
        if tool_name == "bash":
            return  # Rendered in on_tool_result with Kali-style prompt
        if tool_name == "task":
            return  # Sub-agent events streamed via on_subagent_* methods
        skill = _is_skill_load(tool_name, tool_args)
        if skill:
            console.print(f"  [dim]● skill[/dim] [#c678dd]({skill})[/#c678dd]")
            return
        display_tool_call(tool_name, tool_args)

    def on_tool_result(self, tool_name: str, tool_args: dict, content: str) -> None:
        if tool_name == "task":
            return  # Already streamed via sub-agent callbacks
        if tool_name == "write_todos":
            return  # Already rendered as Rich checklist in on_tool_call
        if _is_skill_load(tool_name, tool_args):
            return  # Skill content already indicated in on_tool_call
        if tool_name == "bash":
            tc = {"args": tool_args}

            class _Msg:
                def __init__(self, c):
                    self.content = c

            render_bash_result(tc, _Msg(content), self._last_bash_session_outputs)
        else:
            display_tool_result(content)

    def on_ai_message(self, text: str) -> None:
        display_ai_message(text, agent_name=self._active_agent)

    def on_tool_progress(self, tool_name: str, session: str, status: str, detail: str) -> None:
        if status == "stalled":
            console.print(f"  [dim]\u23f3 '{session}' 세션에서 명령 완료 대기 중...[/dim]")
        elif status == "resumed":
            console.print("  [dim]  └─ 출력 재개됨[/dim]")

    def on_cancelled(self) -> None:
        console.print("\n[yellow]Interrupted — agent stopped. You can continue or /clear.[/yellow]")

    def on_stream_end(self) -> None:
        console.print()

    # ── Sub-agent streaming events ────────────────────────────────────
    # Emitted by StreamingRunnable when Decepticon delegates via task().
    # Visual distinction: cyan header/footer + separator lines.

    def on_subagent_start(self, name: str, prompt: str) -> None:
        console.print(
            f"\n  [bold cyan]\u25b8 {name}[/bold cyan] "
            f"[dim]\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501[/dim]"
        )

    def on_subagent_tool_call(self, name: str, tool_name: str, tool_args: dict) -> None:
        if tool_name == "bash":
            return  # Rendered in on_subagent_tool_result
        skill = _is_skill_load(tool_name, tool_args)
        if skill:
            console.print(f"  [dim]● skill[/dim] [#c678dd]({skill})[/#c678dd]")
            return
        display_tool_call(tool_name, tool_args)

    def on_subagent_tool_result(
        self, name: str, tool_name: str, tool_args: dict, content: str
    ) -> None:
        if _is_skill_load(tool_name, tool_args):
            return  # Skill content already indicated in on_subagent_tool_call
        if tool_name == "bash":
            tc = {"args": tool_args}

            class _Msg:
                def __init__(self, c):
                    self.content = c

            render_bash_result(tc, _Msg(content), self._subagent_bash_outputs)
        else:
            display_tool_result(content)

    def on_subagent_message(self, name: str, text: str) -> None:
        # Show sub-agent name so user knows which agent is speaking
        console.print(f"\n[cyan]\u25cf[/cyan] [bold cyan]{name}[/bold cyan]: ", end="")
        lines = text.strip().split("\n")
        if lines:
            console.print(lines[0])
            if len(lines) > 1:
                from rich.markdown import Markdown

                indented_rest = "\n".join(f"  {line}" for line in lines[1:])
                console.print(Markdown(indented_rest))
        console.print()

    def on_subagent_end(
        self, name: str, elapsed: float, cancelled: bool = False, error: bool = False
    ) -> None:
        if cancelled:
            console.print(
                f"  [yellow]\u25c2 {name} interrupted ({elapsed:.0f}s)[/yellow]\n"
            )
        elif error:
            console.print(
                f"  [red]\u25c2 {name} error ({elapsed:.0f}s)[/red]\n"
            )
        else:
            console.print(
                f"  [bold cyan]\u25c2 {name}[/bold cyan] "
                f"[dim]complete ({elapsed:.0f}s) "
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501[/dim]\n"
            )
