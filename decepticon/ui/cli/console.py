"""Rich Console instance and CLI constants."""

from rich.console import Console

console = Console()

BANNER = r"""
[bold red] ____  _____ ____ _____ ____ _____ ___ ____ ___  _   _ [/bold red]
[bold red]|  _ \| ____/ ___| ____|  _ \_   _|_ _/ ___/ _ \| \ | |[/bold red]
[bold red]| | | |  _|| |   |  _| | |_) || |  | | |  | | | |  \| |[/bold red]
[bold red]| |_| | |__| |___| |___|  __/ | |  | | |__| |_| | |\  |[/bold red]
[bold red]|____/|_____\____|_____|_|    |_| |___\____\___/|_| \_|[/bold red]

"""

HELP_TEXT = """
[bold cyan]Orchestrator:[/bold cyan]
  [yellow]/decepticon[/yellow]  Switch to Decepticon Orchestrator (autonomous kill chain coordination)

[bold cyan]Specialist Agents (interactive mode):[/bold cyan]
  [yellow]/plan[/yellow]       Switch to Planning Agent (generate engagement documents)
  [yellow]/recon[/yellow]      Switch to Recon Agent (reconnaissance & intelligence gathering)
  [yellow]/exploit[/yellow]    Switch to Exploit Agent (initial access & vulnerability exploitation)
  [yellow]/postexploit[/yellow] Switch to PostExploit Agent (post-exploitation: creds, privesc, lateral)

[bold cyan]Ralph Loop (autonomous execution):[/bold cyan]
  [yellow]/ralph <dir>[/yellow]         Start autonomous loop on engagement directory
  [yellow]/ralph status <dir>[/yellow]  Show loop progress
  [yellow]/ralph resume <dir>[/yellow]  Resume interrupted loop
  [yellow]/ralph help[/yellow]          Show ralph loop help

[bold cyan]Session:[/bold cyan]
  [yellow]/clear[/yellow]      Clear screen & conversation history
  [yellow]/compact[/yellow]    Compact conversation context (summarize old tool outputs)
  [yellow]/help[/yellow]       Show this help
  [yellow]/quit[/yellow]       Exit

[dim]All other input is sent to the agent as a prompt.[/dim]
"""
