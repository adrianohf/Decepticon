"""Slash command handlers for the CLI REPL."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from decepticon.ui.cli.console import console

if TYPE_CHECKING:
    from decepticon.core.streaming import StreamingEngine, UIRenderer


def ensure_auth() -> bool:
    """Check if .env has a valid LLM API key.

    Returns True if ready, False if no key found (prints instructions).
    """
    from decepticon.core.config import _project_root

    env_file = _project_root() / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                continue
            for prefix in ("ANTHROPIC_API_KEY=", "OPENAI_API_KEY="):
                if line.startswith(prefix):
                    value = line[len(prefix) :].strip()
                    if value and "your-" not in value and "here" not in value:
                        return True

    console.print("[red]No LLM API key found.[/red]")
    console.print(f"[yellow]Set your API key in:[/yellow] {env_file}")
    console.print("[dim]  ANTHROPIC_API_KEY=sk-ant-...  or  OPENAI_API_KEY=sk-...[/dim]")
    console.print("[dim]  Then restart: docker compose up -d --force-recreate litellm[/dim]\n")
    return False


def switch_agent(name: str, renderer: UIRenderer):
    """Create a fresh agent by name and return (engine, config).

    Raises on failure so the caller can display the error.
    """
    from decepticon.core.streaming import StreamingEngine

    if name == "recon":
        from decepticon.agents import create_recon_agent

        agent = create_recon_agent()
    elif name == "planning":
        from decepticon.agents import create_planner_agent

        agent = create_planner_agent()
    elif name == "exploit":
        from decepticon.agents import create_exploit_agent

        agent = create_exploit_agent()
    elif name == "postexploit":
        from decepticon.agents import create_postexploit_agent

        agent = create_postexploit_agent()
    elif name == "decepticon":
        from decepticon.agents import create_decepticon_agent

        agent = create_decepticon_agent()
    else:
        raise ValueError(f"Unknown agent: {name}")

    new_config = {"configurable": {"thread_id": f"cli-{uuid.uuid4().hex[:8]}"}}
    new_engine = StreamingEngine(agent=agent, renderer=renderer)
    return new_engine, new_config


def handle_ralph(cmd: str, renderer: UIRenderer) -> None:
    """Handle /ralph commands: start, status, resume."""
    from pathlib import Path

    from decepticon.loop import RalphLoop

    parts = cmd.strip().split()
    subcmd = parts[1] if len(parts) > 1 else "start"

    if subcmd == "help":
        console.print(
            "[bold cyan]Ralph Loop Commands:[/bold cyan]\n"
            "  [yellow]/ralph <path>[/yellow]          Start loop on engagement directory\n"
            "  [yellow]/ralph status <path>[/yellow]   Show loop progress\n"
            "  [yellow]/ralph resume <path>[/yellow]   Resume interrupted loop\n"
            "\n[dim]<path> = engagement directory containing roe.json + opplan.json[/dim]"
        )
        return

    if subcmd == "status":
        eng_dir = Path(parts[2]) if len(parts) > 2 else None
        if not eng_dir:
            console.print("[red]Usage: /ralph status <engagement-dir>[/red]")
            return
        try:
            loop = RalphLoop(engagement_dir=eng_dir)
            console.print(loop.status())
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        return

    # /ralph <path> or /ralph start <path> or /ralph resume <path>
    if subcmd in ("start", "resume"):
        eng_dir = Path(parts[2]) if len(parts) > 2 else None
    else:
        # /ralph <path> shorthand
        eng_dir = Path(subcmd)

    if not eng_dir:
        console.print("[red]Usage: /ralph <engagement-dir>[/red]")
        return

    if not eng_dir.exists():
        console.print(f"[red]Directory not found: {eng_dir}[/red]")
        return

    # Check required documents
    for doc in ("roe.json", "opplan.json"):
        if not (eng_dir / doc).exists():
            console.print(
                f"[red]{doc} not found in {eng_dir}.[/red]\n"
                "[dim]Run /plan first to generate engagement documents.[/dim]"
            )
            return

    # Parse max iterations
    max_iter = 20
    for p in parts:
        if p.startswith("--max="):
            try:
                max_iter = int(p.split("=")[1])
            except ValueError:
                pass

    console.print(f"\n[bold red]Starting Ralph Loop[/bold red] — {eng_dir}")
    console.print(f"[dim]Max iterations: {max_iter} | Ctrl+C to pause[/dim]\n")

    try:
        loop = RalphLoop(engagement_dir=eng_dir, max_iterations=max_iter)

        # Show initial status
        console.print(loop.status())
        console.print()

        completed = loop.run(renderer=renderer)

        if completed:
            console.print(
                "\n[bold green]Ralph Loop COMPLETE[/bold green] — " "all objectives passed!"
            )
        else:
            console.print(
                f"\n[yellow]Ralph Loop stopped — max iterations reached.[/yellow]\n"
                f"[dim]Use /ralph resume {eng_dir} to continue.[/dim]"
            )

        # Final status
        console.print()
        console.print(loop.status())

    except KeyboardInterrupt:
        console.print(
            f"\n[yellow]Ralph Loop paused at iteration.[/yellow]\n"
            f"[dim]Use /ralph resume {eng_dir} to continue.[/dim]"
        )
    except Exception as e:
        console.print(f"[bold red]Ralph Loop error:[/bold red] {e}")
