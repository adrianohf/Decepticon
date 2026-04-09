"""Kali CLI wrapper package (legacy compatibility layer).

NOTE:
Runtime operational agents follow the "single bash tool" philosophy and
no longer mount ``KALI_TOOLS`` in their primary tool lists. This package is
kept for compatibility, targeted ingestion workflows, and transition support.

Thin LangChain ``@tool`` wrappers over the most-used Kali binaries.
Each wrapper:

1. Accepts typed params.
2. Builds a safe command line (no shell interpolation of untrusted
   values — we always pass argv lists to the runner).
3. Executes through a ``ToolRunner`` — typically
   ``DockerSandboxRunner`` in production, ``LocalSubprocessRunner`` in
   tests — so the tool is sandboxed via Docker without that being a
   hard dependency.
4. Parses structured output into the shared ``KnowledgeGraph`` when a
   matching ``kg_ingest_*`` function exists, so findings immediately
   become nodes the planner can reason about.

The package does **not** copy the full behaviour of each Kali tool —
it exposes the 90%-common flags with sensible defaults, and returns
the raw stdout alongside any graph enrichment stats so the agent can
drop down to ``bash`` for edge cases.
"""

from __future__ import annotations

import warnings

from decepticon.kali_tools.credential import CREDENTIAL_TOOLS
from decepticon.kali_tools.exploit import EXPLOIT_TOOLS
from decepticon.kali_tools.network import NETWORK_TOOLS
from decepticon.kali_tools.recon import RECON_TOOLS
from decepticon.kali_tools.web_scan import WEB_SCAN_TOOLS

LEGACY_KALI_TOOLS = [
    *RECON_TOOLS,
    *NETWORK_TOOLS,
    *WEB_SCAN_TOOLS,
    *EXPLOIT_TOOLS,
    *CREDENTIAL_TOOLS,
]


def __getattr__(name: str):
    """Compatibility shim for legacy imports.

    ``KALI_TOOLS`` is intentionally deprecated from package exports to
    reinforce the single-bash execution philosophy in runtime agents.
    """
    if name == "KALI_TOOLS":
        warnings.warn(
            "decepticon.kali_tools.KALI_TOOLS is deprecated. "
            "Operational agents must execute via the single `bash` tool. "
            "Use LEGACY_KALI_TOOLS only for migration/tests.",
            DeprecationWarning,
            stacklevel=2,
        )
        return LEGACY_KALI_TOOLS
    raise AttributeError(name)


__all__ = [
    "CREDENTIAL_TOOLS",
    "EXPLOIT_TOOLS",
    "LEGACY_KALI_TOOLS",
    "NETWORK_TOOLS",
    "RECON_TOOLS",
    "WEB_SCAN_TOOLS",
]
