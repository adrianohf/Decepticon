"""CLI interface — Rich-based terminal UI for Decepticon agents."""

from decepticon.ui.cli.console import BANNER, HELP_TEXT, console
from decepticon.ui.cli.renderer import CLIRenderer

__all__ = ["console", "BANNER", "HELP_TEXT", "CLIRenderer"]
