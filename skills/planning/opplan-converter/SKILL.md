---
name: opplan-converter
description: "Convert engagement documents into the machine-readable opplan.json that drives the ralph loop (autonomous red team execution). Handles objective decomposition along kill chain phases, acceptance criteria writing, priority ordering, MITRE ATT&CK mapping per objective, risk assessment, and scope-fit validation. Use this skill whenever the user mentions 'create OPPLAN', 'generate objectives', 'set up the loop', 'convert plan to tasks', or wants to turn a CONOPS into executable objectives, even if they just say 'make it runnable'."
allowed-tools: Read Write Edit
metadata:
  subdomain: planning
  tags: opplan, objectives, ralph-loop, automation
  mitre_attack:
---

# OPPLAN Converter — CONOPS to Ralph Loop Format

The OPPLAN is the **direct analogue of ralph's prd.json** — it's the file the autonomous loop reads each iteration to decide what to do next. Each objective must be completable by one agent in one context window.

## When to Use

- After both `roe.json` and `conops.json` exist
- User wants to convert planning docs into executable tasks
- Starting the autonomous red team loop

## Prerequisites

Read both `roe.json` and `conops.json` first. The RoE constrains what's allowed; the CONOPS defines the kill chain and threat profile.

See `../references/schema-quick-reference.md` for the `OPPLAN` and `Objective` schema fields, valid status values, and helper methods.

## Workflow

### Step 1: Extract Kill Chain from CONOPS

Read the CONOPS kill chain phases. Only create objectives for authorized phases.

### Step 2: Decompose into Objectives

Each objective must follow the **one context window** rule — if an agent can't complete it in a single session, it's too big. Split it.

See `references/objective-templates.md` for recon-phase templates and `references/objective-rules.md` for the complete decomposition rules.

**ID Convention:** `OBJ-{PHASE_PREFIX}-{NUMBER}`

| Phase | Prefix |
|-------|--------|
| recon | REC |
| weaponize | WPN |
| deliver | DLV |
| exploit | EXP |
| install | INS |
| c2 | C2 |
| exfiltrate | EXF |

### Step 3: Write Acceptance Criteria

Every objective MUST have three mandatory criteria types:

1. **Scope check** — "All targets verified against roe.json in-scope list"
2. **OPSEC check** — At least one OPSEC-related criterion (rate limit, timing, etc.)
3. **Output persistence** — "Results saved to /workspace/..." with specific file path

Beyond these, add criteria specific to what the objective accomplishes. Every criterion must be mechanically verifiable — no vague statements like "good coverage."

### Step 4: Assign Metadata

For each objective:
- **priority** — Sequential, respects kill chain ordering and dependencies
- **mitre** — Primary MITRE ATT&CK technique ID
- **risk_level** — low (passive), medium (active scanning), high (exploitation), critical (service disruption risk)
- **opsec_notes** — Specific OPSEC considerations

### Step 5: Generate Documents

1. `opplan.json` — matching `OPPLAN` schema from `decepticon.core.schemas`
2. `deconfliction.json` — matching `DeconflictionPlan` schema

### Step 6: Validate

See `references/objective-rules.md` validation checklist before finalizing.

## Output

Write both JSON files to the engagement directory, then present a summary table showing all objectives with phase, priority, title, risk level, and MITRE mapping.
