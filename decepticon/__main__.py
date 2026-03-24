"""Decepticon entry point: python -m decepticon

The primary CLI is the Ink.js client at clients/cli/.
This module launches the LangGraph server that the CLI connects to.
"""

import subprocess
import sys


def main():
    """Start the LangGraph development server."""
    try:
        subprocess.run(
            ["langgraph", "dev"],
            check=True,
        )
    except FileNotFoundError:
        print("Error: langgraph CLI not found. Install with: pip install langgraph-cli[inmem]")
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
