"""Guardrails for the single-bash execution philosophy.

Operational lanes should expose ``bash`` for command execution and must not
re-introduce legacy Kali wrapper tool bundles into runtime tool lists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

OPERATIONAL_AGENT_FILES = [
    REPO_ROOT / "decepticon/agents/recon.py",
    REPO_ROOT / "decepticon/agents/exploit.py",
    REPO_ROOT / "decepticon/agents/postexploit.py",
    REPO_ROOT / "decepticon/agents/ad_operator.py",
    REPO_ROOT / "decepticon/agents/cloud_hunter.py",
]


@pytest.mark.parametrize("path", OPERATIONAL_AGENT_FILES)
def test_operational_agents_do_not_import_kali_wrappers(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert "decepticon.kali_tools" not in source
    assert "KALI_TOOLS" not in source


@pytest.mark.parametrize("path", OPERATIONAL_AGENT_FILES)
def test_operational_agents_include_bash_in_tool_surface(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    match = re.search(r"tools\s*=\s*\[(.*?)\]", source, flags=re.DOTALL)
    assert match is not None, f"tools list not found in {path}"
    tools_expr = match.group(1)
    assert "bash" in tools_expr, f"bash missing from tools list in {path}"
