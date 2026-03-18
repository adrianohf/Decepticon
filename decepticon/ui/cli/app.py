"""Decepticon CLI — interactive agent debug interface."""

import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

import click
from rich.prompt import Prompt

from decepticon.core.streaming import StreamingEngine
from decepticon.ui.cli.commands import ensure_auth, handle_ralph, switch_agent
from decepticon.ui.cli.console import BANNER, HELP_TEXT, console
from decepticon.ui.cli.context import compact_context
from decepticon.ui.cli.renderer import CLIRenderer
from decepticon.ui.cli.startup import run_startup

# ── Context budget monitoring ──────────────────────────────────────────
# Warn when conversation exceeds this many turns (context degradation risk)
TURN_WARNING_THRESHOLD = 15


@click.command()
def main():
    """Decepticon Agent CLI — real-time agent execution viewer."""
    console.print(BANNER)

    # Auth gate: ensure credentials exist before starting agent
    if not ensure_auth():
        console.print("[red]Setup incomplete. Run 'decepticon init' to configure.[/red]")
        sys.exit(1)

    renderer = CLIRenderer()

    # Start with planning agent in chat mode
    result = run_startup(mode="planning")
    if result is None:
        sys.exit(1)

    agent, config = result
    active_agent_name = "planning"
    renderer.set_active_agent(active_agent_name)
    engine = StreamingEngine(agent=agent, renderer=renderer)

    console.print("\n[dim]Type your prompt. /help for commands.[/dim]\n")

    turn_count = 0

    while True:
        try:
            label = f"[bold red]you[/bold red] [dim]({active_agent_name})[/dim]"
            user_input = Prompt.ask(label)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye![/dim]")
            break

        # Sanitize surrogates from user input — Rich Prompt can capture
        # invalid codepoints when the user types/deletes rapidly
        user_input = user_input.encode("utf-8", errors="surrogateescape").decode(
            "utf-8", errors="replace"
        )
        cmd = user_input.strip()
        if not cmd:
            continue

        if cmd in ("/quit", "/exit"):
            console.print("[dim]Bye![/dim]")
            break
        elif cmd == "/help":
            console.print(HELP_TEXT)
            continue
        elif cmd == "/clear":
            console.clear()
            console.print(BANNER)
            config = {"configurable": {"thread_id": f"cli-{uuid.uuid4().hex[:8]}"}}
            turn_count = 0
            engine._turn_count = 0
            console.print(
                f"[dim]Conversation cleared. Active agent: {active_agent_name}[/dim]\n"
            )
            continue
        elif cmd == "/compact":
            compact_context(engine, config)
            continue
        elif cmd == "/plan":
            try:
                engine, config = switch_agent("planning", renderer)
                active_agent_name = "planning"
                renderer.set_active_agent(active_agent_name)
                turn_count = 0
                console.print("[green]Switched to Planning Agent.[/green]")
                console.print(
                    "[dim]Generate engagement documents: RoE → CONOPS → OPPLAN[/dim]\n"
                )
            except Exception as e:
                console.print(f"[red]Failed to switch: {e}[/red]")
            continue
        elif cmd == "/recon":
            try:
                engine, config = switch_agent("recon", renderer)
                active_agent_name = "recon"
                renderer.set_active_agent(active_agent_name)
                turn_count = 0
                console.print("[green]Switched to Recon Agent.[/green]\n")
            except Exception as e:
                console.print(f"[red]Failed to switch: {e}[/red]")
            continue
        elif cmd == "/exploit":
            try:
                engine, config = switch_agent("exploit", renderer)
                active_agent_name = "exploit"
                renderer.set_active_agent(active_agent_name)
                turn_count = 0
                console.print("[green]Switched to Exploit Agent.[/green]")
                console.print("[dim]Initial access & vulnerability exploitation[/dim]\n")
            except Exception as e:
                console.print(f"[red]Failed to switch: {e}[/red]")
            continue
        elif cmd == "/postexploit":
            try:
                engine, config = switch_agent("postexploit", renderer)
                active_agent_name = "postexploit"
                renderer.set_active_agent(active_agent_name)
                turn_count = 0
                console.print("[green]Switched to PostExploit Agent.[/green]")
                console.print(
                    "[dim]Post-exploitation: creds → privesc → lateral movement[/dim]\n"
                )
            except Exception as e:
                console.print(f"[red]Failed to switch: {e}[/red]")
            continue
        elif cmd == "/decepticon":
            try:
                engine, config = switch_agent("decepticon", renderer)
                active_agent_name = "decepticon"
                renderer.set_active_agent(active_agent_name)
                turn_count = 0
                console.print("[green]Switched to Decepticon Orchestrator.[/green]")
                console.print(
                    "[dim]Autonomous kill chain orchestration — delegates to planner/recon/exploit/postexploit[/dim]\n"
                )
            except Exception as e:
                console.print(f"[red]Failed to switch: {e}[/red]")
            continue
        elif cmd.startswith("/ralph"):
            handle_ralph(cmd, renderer)
            continue
        elif cmd.startswith("/"):
            console.print(f"[yellow]Unknown command: {cmd}[/yellow]  (try /help)")
            continue

        console.print()
        turn_count += 1

        # Context budget warning at threshold
        if turn_count == TURN_WARNING_THRESHOLD:
            console.print(
                "[yellow][Context Warning] Long conversation detected. "
                "Use /compact to free context budget or /clear to start fresh.[/yellow]\n"
            )

        try:
            engine.run(cmd, config)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Agent error:[/bold red] {e}")


if __name__ == "__main__":
    main()
