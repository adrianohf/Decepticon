"""Red team engagement document schemas.

Defines the machine-readable document set for planning and executing
red team engagements. These map to the military-style planning hierarchy:

  RoE     → legal scope & boundaries       (guard rail, checked every iteration)
  CONOPS  → operational concept & threat    (strategic context)
  OPPLAN  → tactical objectives & status    (ralph loop task tracker)

The OPPLAN is the direct analogue of ralph's prd.json — it drives the
autonomous loop, with each objective checked off as it passes validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────

class EngagementType(StrEnum):
    EXTERNAL = "external"
    INTERNAL = "internal"
    HYBRID = "hybrid"
    ASSUMED_BREACH = "assumed-breach"
    PHYSICAL = "physical"


class ObjectivePhase(StrEnum):
    """Kill chain phases for objective ordering."""

    RECON = "recon"
    WEAPONIZE = "weaponize"
    DELIVER = "deliver"
    EXPLOIT = "exploit"
    INSTALL = "install"
    C2 = "c2"
    EXFILTRATE = "exfiltrate"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ObjectiveStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in-progress"
    PASSED = "passed"
    BLOCKED = "blocked"
    OUT_OF_SCOPE = "out-of-scope"


# ── RoE (Rules of Engagement) ────────────────────────────────────────

class ScopeEntry(BaseModel):
    """A single in-scope or out-of-scope target."""

    target: str = Field(description="Domain, IP range (CIDR), or asset identifier")
    type: str = Field(description="domain, ip-range, cloud-resource, physical, etc.")
    notes: str = ""


class EscalationContact(BaseModel):
    """Emergency or escalation contact."""

    name: str
    role: str
    channel: str = Field(description="Phone, email, Slack, etc.")
    available: str = Field(default="24/7", description="Availability window")


class RoE(BaseModel):
    """Rules of Engagement — legally binding scope and boundaries.

    Checked at the start of every ralph loop iteration as a guard rail.
    """

    engagement_name: str
    client: str
    start_date: str
    end_date: str
    engagement_type: EngagementType
    testing_window: str = Field(
        description="Authorized testing hours, e.g. 'Mon-Fri 09:00-18:00 KST'"
    )

    # Scope
    in_scope: list[ScopeEntry] = Field(default_factory=list)
    out_of_scope: list[ScopeEntry] = Field(default_factory=list)

    # Boundaries
    prohibited_actions: list[str] = Field(
        default_factory=lambda: [
            "Denial of Service (DoS/DDoS)",
            "Social engineering of employees (unless authorized)",
            "Physical access attempts (unless authorized)",
            "Data exfiltration of real customer data",
            "Modification or deletion of production data",
        ]
    )
    permitted_actions: list[str] = Field(default_factory=list)

    # Escalation
    escalation_contacts: list[EscalationContact] = Field(default_factory=list)
    incident_procedure: str = Field(
        default="Stop immediately, document the incident, notify engagement lead within 15 minutes."
    )

    # Legal
    authorization_reference: str = Field(
        default="", description="Reference to signed authorization letter or contract"
    )

    # Metadata
    version: str = "1.0"
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── CONOPS (Concept of Operations) ───────────────────────────────────

class ThreatActor(BaseModel):
    """Threat actor profile to emulate."""

    name: str = Field(description="Actor name or archetype, e.g. 'APT29', 'Opportunistic External'")
    sophistication: str = Field(description="low, medium, high, nation-state")
    motivation: str = Field(description="financial, espionage, disruption, hacktivism")
    initial_access: list[str] = Field(
        default_factory=list,
        description="Expected initial access techniques (MITRE IDs)"
    )
    ttps: list[str] = Field(
        default_factory=list,
        description="Key MITRE ATT&CK technique IDs this actor uses"
    )


class KillChainPhase(BaseModel):
    """A phase in the engagement kill chain."""

    phase: ObjectivePhase
    description: str
    success_criteria: str
    tools: list[str] = Field(default_factory=list)


class CONOPS(BaseModel):
    """Concept of Operations — strategic engagement overview.

    Readable by both technical operators and non-technical stakeholders.
    """

    engagement_name: str
    executive_summary: str = Field(
        description="2-3 sentence overview a CEO could understand"
    )

    # Threat model
    threat_actors: list[ThreatActor] = Field(default_factory=list)
    attack_narrative: str = Field(
        default="",
        description="Story-form description of the simulated attack scenario"
    )

    # Kill chain
    kill_chain: list[KillChainPhase] = Field(default_factory=list)

    # Operational
    methodology: str = Field(default="PTES + MITRE ATT&CK framework")
    communication_plan: str = Field(
        default="",
        description="How red cell communicates with client and internally"
    )
    deconfliction_method: str = Field(
        default="",
        description="How to distinguish red team activity from real attacks"
    )

    # Timeline
    phases_timeline: dict[str, str] = Field(
        default_factory=dict,
        description="Phase name → date range mapping"
    )

    # Success criteria
    success_criteria: list[str] = Field(default_factory=list)


# ── Deconfliction Plan ───────────────────────────────────────────────

class DeconflictionEntry(BaseModel):
    """A deconfliction identifier for red team activity."""

    type: str = Field(description="source-ip, user-agent, tool-hash, time-window, etc.")
    value: str
    description: str = ""


class DeconflictionPlan(BaseModel):
    """Deconfliction plan — separating red team activity from real threats."""

    engagement_name: str
    identifiers: list[DeconflictionEntry] = Field(default_factory=list)
    notification_procedure: str = Field(
        default="Red team lead notifies SOC 30 minutes before active scanning begins."
    )
    soc_contact: str = ""
    deconfliction_code: str = Field(
        default="",
        description="Shared secret code for real-time deconfliction calls"
    )


# ── OPPLAN (Operations Plan) — the ralph loop driver ─────────────────

class Objective(BaseModel):
    """A single engagement objective — analogous to ralph's user story.

    Each objective must be completable in ONE agent context window.
    The ralph loop picks the highest-priority objective where status != 'passed'.
    """

    id: str = Field(description="Unique ID, e.g. OBJ-001")
    phase: ObjectivePhase
    title: str
    description: str
    acceptance_criteria: list[str] = Field(
        description="Verifiable criteria — each must be checkable"
    )
    priority: int = Field(
        description="Execution order (1 = first). Respects kill chain dependencies."
    )
    status: ObjectiveStatus = ObjectiveStatus.PENDING
    mitre: str = Field(default="", description="Primary MITRE ATT&CK technique ID")
    risk_level: RiskLevel = RiskLevel.LOW
    opsec_notes: str = Field(
        default="", description="OPSEC considerations specific to this objective"
    )
    notes: str = ""


class OPPLAN(BaseModel):
    """Operations Plan — the tactical task tracker for the ralph loop.

    Direct analogue of ralph's prd.json. The autonomous loop reads this
    file each iteration, picks the next objective, executes it, and
    updates the status.
    """

    engagement_name: str
    branch_name: str = Field(
        description="Git branch for this engagement, e.g. 'engage/acme-external-2026-03'"
    )
    threat_profile: str = Field(
        description="Short threat actor summary for context injection each iteration"
    )
    kill_chain: list[str] = Field(
        default_factory=lambda: [p.value for p in ObjectivePhase],
        description="Kill chain phase ordering"
    )
    objectives: list[Objective] = Field(default_factory=list)

    def next_objective(self) -> Objective | None:
        """Return the highest-priority objective that hasn't passed yet."""
        pending = [
            o for o in self.objectives
            if o.status in (ObjectiveStatus.PENDING, ObjectiveStatus.IN_PROGRESS)
        ]
        if not pending:
            return None
        return min(pending, key=lambda o: o.priority)

    def is_complete(self) -> bool:
        """Check if all objectives have passed."""
        return all(
            o.status in (ObjectiveStatus.PASSED, ObjectiveStatus.OUT_OF_SCOPE)
            for o in self.objectives
        )

    def progress_summary(self) -> str:
        """Return a one-line progress summary."""
        total = len(self.objectives)
        passed = sum(1 for o in self.objectives if o.status == ObjectiveStatus.PASSED)
        return f"{passed}/{total} objectives completed"


# ── Engagement Bundle ─────────────────────────────────────────────────

class EngagementBundle(BaseModel):
    """Complete engagement document set.

    The planning agent generates all four documents as a unit.
    The ralph loop reads roe + opplan each iteration.
    """

    roe: RoE
    conops: CONOPS
    opplan: OPPLAN
    deconfliction: DeconflictionPlan

    def save(self, directory: str) -> dict[str, str]:
        """Save all documents as JSON files to a directory.

        Returns a mapping of document type → file path.
        """
        import json
        from pathlib import Path

        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)

        files = {}
        for name, doc in [
            ("roe", self.roe),
            ("conops", self.conops),
            ("opplan", self.opplan),
            ("deconfliction", self.deconfliction),
        ]:
            path = out_dir / f"{name}.json"
            path.write_text(
                json.dumps(doc.model_dump(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            files[name] = str(path)

        # Initialize empty findings.txt
        findings_path = out_dir / "findings.txt"
        if not findings_path.exists():
            findings_path.write_text(
                f"# Findings Log — {self.roe.engagement_name}\n"
                f"# Started: {datetime.now().isoformat()}\n"
                "---\n\n"
                "## Codebase Patterns\n"
                "- (none yet)\n"
                "---\n",
                encoding="utf-8",
            )
            files["findings"] = str(findings_path)

        return files
