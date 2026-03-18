"""Animated startup sequence using Rich Live display."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from rich.live import Live
from rich.text import Text

from decepticon.backends import check_sandbox_running
from decepticon.ui.cli.console import console

# Step states
_PENDING = "pending"
_RUNNING = "running"
_DONE = "done"
_FAILED = "failed"
_SKIPPED = "skipped"

# Icons per state
_ICONS = {
    _PENDING: ("○", "dim"),
    _RUNNING: ("◌", "bold yellow"),
    _DONE: ("●", "bold green"),
    _FAILED: ("✗", "bold red"),
    _SKIPPED: ("○", "dim yellow"),
}


class _Step:
    __slots__ = ("label", "state", "detail")

    def __init__(self, label: str):
        self.label = label
        self.state = _PENDING
        self.detail: str | None = None

    def render(self) -> Text:
        icon, style = _ICONS[self.state]
        t = Text(f"  {icon} ", style=style)
        t.append(self.label, style="bold white" if self.state == _RUNNING else "white")
        if self.state == _DONE:
            t.append("  ✓", style="bold green")
        elif self.state == _FAILED and self.detail:
            t.append(f"  — {self.detail}", style="red")
        elif self.state == _SKIPPED and self.detail:
            t.append(f"  — {self.detail}", style="dim yellow")
        return t


def _build_display(steps: list[_Step]) -> Text:
    out = Text()
    for i, step in enumerate(steps):
        out.append_text(step.render())
        if i < len(steps) - 1:
            out.append("\n")
    return out


def _find_engagements() -> list[Path]:
    """Scan for existing engagement directories with opplan.json."""
    candidates = []
    workspace = Path("/workspace/engagements")
    if workspace.exists():
        for d in workspace.iterdir():
            if d.is_dir() and (d / "opplan.json").exists():
                candidates.append(d)
    # Also check local engagements/ directory
    local = Path("engagements")
    if local.exists():
        for d in local.iterdir():
            if d.is_dir() and (d / "opplan.json").exists():
                candidates.append(d)
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def run_startup(mode: str = "recon") -> tuple[Any, dict] | None:
    """Run the startup sequence with animated status steps.

    Args:
        mode: "recon", "planning", "exploit", "postexploit", or "decepticon".

    Returns (agent, config) on success, or None on failure.
    """
    steps = [
        _Step("Docker sandbox"),
        _Step("LLM connection"),
        _Step(f"Agent initialization ({mode})"),
    ]

    agent = None
    config = None
    failed = False

    with Live(_build_display(steps), console=console, refresh_per_second=8, transient=True) as live:
        # Step 1: Sandbox (required for all modes — planner also writes to container)
        steps[0].state = _RUNNING
        live.update(_build_display(steps))

        if not check_sandbox_running():
            steps[0].state = _FAILED
            steps[0].detail = "container not running — run: docker compose up -d"
            live.update(_build_display(steps))
            failed = True
        else:
            steps[0].state = _DONE
            live.update(_build_display(steps))

        if failed:
            pass
        else:
            # Step 2: LLM
            steps[1].state = _RUNNING
            live.update(_build_display(steps))

            try:
                if mode == "planning":
                    from decepticon.agents import create_planner_agent
                    agent = create_planner_agent()
                elif mode == "decepticon":
                    from decepticon.agents import create_decepticon_agent
                    agent = create_decepticon_agent()
                elif mode == "exploit":
                    from decepticon.agents import create_exploit_agent
                    agent = create_exploit_agent()
                elif mode == "postexploit":
                    from decepticon.agents import create_postexploit_agent
                    agent = create_postexploit_agent()
                else:
                    from decepticon.agents import create_recon_agent
                    agent = create_recon_agent()

                steps[1].state = _DONE
                live.update(_build_display(steps))
            except Exception as e:
                steps[1].state = _FAILED
                steps[1].detail = str(e)
                live.update(_build_display(steps))
                failed = True

            if not failed:
                # Step 3: Agent config
                steps[2].state = _RUNNING
                live.update(_build_display(steps))

                config = {"configurable": {"thread_id": f"cli-{uuid.uuid4().hex[:8]}"}}
                steps[2].state = _DONE
                live.update(_build_display(steps))

    # Print final state (transient=True clears live, so re-print)
    console.print(_build_display(steps))

    if failed:
        return None

    return agent, config
