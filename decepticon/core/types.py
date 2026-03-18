"""Decepticon common types and enums."""

from __future__ import annotations

from enum import StrEnum


class AgentRole(StrEnum):
    """Roles for specialized agents."""

    RECON = "recon"
    PLANNER = "planner"
    PLANNING = "planning"  # backward compat alias — maps to same config key
    EXPLOIT = "exploit"
    POSTEXPLOIT = "postexploit"
    DECEPTICON = "decepticon"
