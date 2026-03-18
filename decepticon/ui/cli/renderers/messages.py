"""Tool call, result, and AI message renderers (Rich-based)."""

import re

from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text

from decepticon.ui.cli.console import console


def display_todo_checklist(todos: list[dict]):
    """Render write_todos as a visual checklist."""
    from rich.panel import Panel
    from rich.table import Table

    table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    table.add_column(width=3)
    table.add_column()

    for item in todos:
        content = item.get("content", "")
        status = item.get("status", "pending")
        if status == "completed":
            icon = "[green]✔[/green]"
            style = "dim"
        elif status == "in_progress":
            icon = "[yellow]◉[/yellow]"
            style = "bold"
        else:
            icon = "[dim]○[/dim]"
            style = ""
        table.add_row(icon, Text(content, style=style))

    console.print()
    console.print(Panel(table, title="[bold #c678dd]Todo[/bold #c678dd]", border_style="dim", expand=False))


def display_tool_call(tool_name: str, tool_args: dict):
    """Render tool call — 2-tone: function name (purple) + args (gray)."""
    # Special rendering for write_todos
    if tool_name == "write_todos" and "todos" in tool_args:
        display_todo_checklist(tool_args["todos"])
        return

    t = Text("● ", style="dim")
    t.append(tool_name, style="bold #c678dd")
    t.append("(", style="dim")

    parts = []
    for k, v in tool_args.items():
        if not v:
            continue
        part = Text(k, style="#abb2bf")
        part.append("=", style="dim")
        if isinstance(v, str):
            part.append(f'"{v}"', style="#98c379")
        else:
            part.append(str(v), style="#d19a66")
        parts.append(part)

    for i, part in enumerate(parts):
        t.append_text(part)
        if i < len(parts) - 1:
            t.append(", ", style="dim")

    t.append(")", style="dim")
    console.print(t)


def display_tool_result(result: str):
    """Render tool result with monokai background."""
    clean = result.strip()
    if not clean:
        return

    # Re-align cat -n style line numbers
    lines = clean.split("\n")
    numbered = all(re.match(r"^\s*\d+\t", line) for line in lines[:3] if line.strip())
    if numbered and lines:
        max_num = 0
        for line in lines:
            m = re.match(r"^\s*(\d+)\t", line)
            if m:
                max_num = max(max_num, len(m.group(1)))
        aligned = []
        for line in lines:
            m = re.match(r"^\s*(\d+)\t(.*)", line)
            if m:
                aligned.append(f"{m.group(1):>{max_num}}  {m.group(2)}")
            else:
                aligned.append(line)
        clean = "\n".join(aligned)

    console.print()
    console.print(Syntax(clean, "text", theme="monokai", word_wrap=True))
    console.print()


def display_ai_message(text: str, agent_name: str = ""):
    """Render AI response with agent name label."""
    if agent_name:
        console.print(f"\n[blue]●[/blue] [bold blue]{agent_name}[/bold blue]: ", end="")
    else:
        console.print("\n[blue]●[/blue] ", end="")

    lines = text.strip().split("\n")
    if lines:
        console.print(lines[0])
        if len(lines) > 1:
            indented_rest = "\n".join(f"  {line}" for line in lines[1:])
            console.print(Markdown(indented_rest))
    console.print()
