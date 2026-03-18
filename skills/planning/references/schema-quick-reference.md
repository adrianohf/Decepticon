# Schema Quick Reference

All planning documents are defined as Pydantic models in `decepticon/core/schemas.py`. This reference summarizes the required fields and valid values for each schema so skills can generate valid documents without needing to read the source code directly.

> **Source of truth**: `decepticon.core.schemas` — if this reference diverges from the code, the code wins.

## RoE (Rules of Engagement)

```
RoE
├── engagement_name: str (required)
├── client: str (required)
├── start_date: str (required, ISO date)
├── end_date: str (required, ISO date, must be > start_date)
├── engagement_type: EngagementType (required)
│   └── "external" | "internal" | "hybrid" | "assumed-breach" | "physical"
├── testing_window: str (required, must include timezone)
├── in_scope: list[ScopeEntry] (at least 1 required)
│   └── ScopeEntry { target: str, type: str, notes: str }
├── out_of_scope: list[ScopeEntry]
│   └── ScopeEntry { target: str, type: str, notes: str }
├── prohibited_actions: list[str] (5 defaults always included)
│   └── Defaults: DoS, social engineering, physical access, data exfiltration, production data modification
├── permitted_actions: list[str]
├── escalation_contacts: list[EscalationContact] (at least 2 required)
│   └── EscalationContact { name: str, role: str, channel: str, available: str }
├── incident_procedure: str (required, non-empty)
├── authorization_reference: str (required, non-empty)
├── version: str (default "1.0")
└── last_updated: str (ISO datetime, auto-generated)
```

## CONOPS (Concept of Operations)

```
CONOPS
├── engagement_name: str (required)
├── executive_summary: str (required, non-technical, CEO-readable)
├── threat_actors: list[ThreatActor]
│   └── ThreatActor
│       ├── name: str (actor name/archetype)
│       ├── sophistication: str ("low" | "medium" | "high" | "nation-state")
│       ├── motivation: str ("financial" | "espionage" | "disruption" | "hacktivism")
│       ├── initial_access: list[str] (MITRE technique IDs)
│       └── ttps: list[str] (MITRE technique IDs)
├── attack_narrative: str (story-form scenario)
├── kill_chain: list[KillChainPhase]
│   └── KillChainPhase
│       ├── phase: ObjectivePhase
│       ├── description: str
│       ├── success_criteria: str
│       └── tools: list[str]
├── methodology: str (default "PTES + MITRE ATT&CK framework")
├── communication_plan: str (frequency + channel)
├── deconfliction_method: str
├── phases_timeline: dict[str, str] (phase → date range, absolute dates only)
└── success_criteria: list[str] (at least 2 required)
```

## DeconflictionPlan

```
DeconflictionPlan
├── engagement_name: str (required)
├── identifiers: list[DeconflictionEntry]
│   └── DeconflictionEntry
│       ├── type: str ("source-ip" | "user-agent" | "tool-hash" | "time-window" | etc.)
│       ├── value: str
│       └── description: str
├── notification_procedure: str
├── soc_contact: str
└── deconfliction_code: str (shared secret)
```

## OPPLAN (Operations Plan)

```
OPPLAN
├── engagement_name: str (required)
├── branch_name: str (required, convention: "engage/<client>-<type>-<date>")
├── threat_profile: str (required, one-sentence threat actor summary)
├── kill_chain: list[str] (phase ordering)
│   └── Valid phases: "recon" | "weaponize" | "deliver" | "exploit" | "install" | "c2" | "exfiltrate"
└── objectives: list[Objective]
    └── Objective
        ├── id: str (required, convention: "OBJ-{PHASE_PREFIX}-{NUMBER}")
        ├── phase: ObjectivePhase (required)
        ├── title: str (required)
        ├── description: str (required)
        ├── acceptance_criteria: list[str] (required, must include scope/OPSEC/output checks)
        ├── priority: int (required, sequential, respects kill chain)
        ├── status: ObjectiveStatus (default "pending")
        │   └── "pending" | "in-progress" | "passed" | "blocked" | "out-of-scope"
        ├── mitre: str (MITRE ATT&CK technique ID)
        ├── risk_level: RiskLevel (default "low")
        │   └── "low" | "medium" | "high" | "critical"
        ├── opsec_notes: str
        └── notes: str
```

## EngagementBundle

The complete document set. Use `EngagementBundle.save(directory)` to write all four JSON files at once.

```
EngagementBundle
├── roe: RoE
├── conops: CONOPS
├── opplan: OPPLAN
└── deconfliction: DeconflictionPlan

.save(directory) → writes roe.json, conops.json, opplan.json, deconfliction.json + findings.txt
```

## OPPLAN Helper Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `next_objective()` | `Objective \| None` | Highest-priority pending/in-progress objective |
| `is_complete()` | `bool` | True if all objectives passed or out-of-scope |
| `progress_summary()` | `str` | e.g. "5/10 objectives completed" |
