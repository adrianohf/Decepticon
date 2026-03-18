"""Ralph Loop — autonomous red team execution engine.

Implements the ralph pattern adapted for red team engagements:

  Original ralph:  prd.json → user stories → typecheck/test → commit
  Decepticon:      opplan.json → objectives → acceptance criteria → findings

Each iteration:
  1. Load roe.json (guard rail) + opplan.json (task tracker)
  2. Pick next objective (highest priority, status != passed)
  3. Select agent by phase: recon → Recon, exploit → Exploit, c2/install → PostExploit
  4. Spawn FRESH agent (clean context window)
  5. Inject: objective + threat profile + findings.txt + roe scope
  6. Agent executes the objective
  7. Validate acceptance criteria
  8. Update opplan.json status + append to findings.txt
  9. Repeat until all objectives passed or max iterations reached

State flows between iterations via FILES, not agent memory:
  - opplan.json: which objectives are done (passes: true/false equivalent)
  - findings.txt: append-only log of discoveries (like progress.txt)
  - roe.json: immutable guard rail checked every iteration
  - /workspace/recon/*: scan artifacts persist in Docker sandbox
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from decepticon.core.logging import get_logger
from decepticon.core.schemas import (
    OPPLAN,
    Objective,
    ObjectiveStatus,
    RoE,
)

log = get_logger("loop")

# Completion signal — agent outputs this when all objectives are done
COMPLETION_PROMISE = "<promise>COMPLETE</promise>"

# Default limits
DEFAULT_MAX_ITERATIONS = 20


@dataclass
class LoopState:
    """Persistent state for the ralph loop, saved to disk between iterations."""

    engagement_dir: Path
    iteration: int = 0
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    active: bool = False
    completed: bool = False

    # Loaded documents (refreshed each iteration)
    _roe: RoE | None = field(default=None, repr=False)
    _opplan: OPPLAN | None = field(default=None, repr=False)

    @property
    def roe(self) -> RoE:
        if self._roe is None:
            self._roe = self._load_doc("roe.json", RoE)
        return self._roe

    @property
    def opplan(self) -> OPPLAN:
        if self._opplan is None:
            self._opplan = self._load_doc("opplan.json", OPPLAN)
        return self._opplan

    def _load_doc(self, filename: str, model_cls: type):
        path = self.engagement_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"{filename} not found in {self.engagement_dir}. "
                f"Run /plan first to generate engagement documents."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return model_cls(**data)

    def reload(self) -> None:
        """Force reload documents from disk (called each iteration)."""
        self._roe = None
        self._opplan = None

    def save_opplan(self) -> None:
        """Persist the current opplan state to disk."""
        path = self.engagement_dir / "opplan.json"
        path.write_text(
            json.dumps(self.opplan.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def append_findings(self, objective: Objective, findings: str) -> None:
        """Append iteration findings to the append-only findings log."""
        path = self.engagement_dir / "findings.txt"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n---\n"
            f"## Iteration {self.iteration} — {objective.id}: {objective.title}\n"
            f"**Time**: {timestamp}\n"
            f"**Phase**: {objective.phase}\n"
            f"**MITRE**: {objective.mitre}\n"
            f"**Status**: {objective.status}\n\n"
            f"{findings}\n"
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)

    def read_findings(self) -> str:
        """Read the findings log for context injection."""
        path = self.engagement_dir / "findings.txt"
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8")
        # Keep last ~3000 chars to fit in context window
        if len(content) > 3000:
            return "...(truncated)...\n" + content[-3000:]
        return content

    def save_loop_state(self) -> None:
        """Persist loop metadata to disk for resumption."""
        path = self.engagement_dir / ".loop_state.json"
        path.write_text(
            json.dumps(
                {
                    "iteration": self.iteration,
                    "max_iterations": self.max_iterations,
                    "active": self.active,
                    "completed": self.completed,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load_or_create(
        cls, engagement_dir: Path, max_iterations: int = DEFAULT_MAX_ITERATIONS
    ) -> "LoopState":
        """Load existing loop state or create a new one."""
        state_path = engagement_dir / ".loop_state.json"
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return cls(
                engagement_dir=engagement_dir,
                iteration=data.get("iteration", 0),
                max_iterations=max_iterations,
                active=data.get("active", False),
                completed=data.get("completed", False),
            )
        return cls(engagement_dir=engagement_dir, max_iterations=max_iterations)


def _build_iteration_prompt(state: LoopState, objective: Objective) -> str:
    """Build the prompt injected into a fresh recon agent each iteration.

    This is the key context engineering decision — each fresh agent gets:
    1. The specific objective to execute (small, focused)
    2. RoE scope boundaries (guard rail)
    3. Threat profile context (from opplan)
    4. Previous findings (cross-iteration memory)
    5. Explicit completion signal instructions
    """
    roe = state.roe
    opplan = state.opplan

    # Build scope summary from RoE
    in_scope = "\n".join(
        f"  - {s.target} ({s.type}){' — ' + s.notes if s.notes else ''}" for s in roe.in_scope
    )
    out_scope = "\n".join(
        f"  - {s.target} ({s.type}){' — ' + s.notes if s.notes else ''}" for s in roe.out_of_scope
    )

    # Build acceptance criteria checklist
    criteria = "\n".join(f"  - [ ] {c}" for c in objective.acceptance_criteria)

    # Previous findings for context
    findings = state.read_findings()
    findings_section = ""
    if findings:
        findings_section = f"""
<PREVIOUS_FINDINGS>
{findings}
</PREVIOUS_FINDINGS>
"""

    # Progress summary
    progress = opplan.progress_summary()
    completed_objs = [
        f"  - {o.id}: {o.title} [PASSED]"
        for o in opplan.objectives
        if o.status == ObjectiveStatus.PASSED
    ]
    completed_section = "\n".join(completed_objs) if completed_objs else "  (none yet)"

    prompt = f"""<RALPH_LOOP_ITERATION>
## Iteration {state.iteration} / {state.max_iterations}
## Progress: {progress}

### Completed Objectives:
{completed_section}

</RALPH_LOOP_ITERATION>

<CURRENT_OBJECTIVE>
**{objective.id}**: {objective.title}
**Phase**: {objective.phase}
**MITRE ATT&CK**: {objective.mitre}
**Risk Level**: {objective.risk_level}
**OPSEC Notes**: {objective.opsec_notes or "None"}

**Description**:
{objective.description}

**Acceptance Criteria** (ALL must pass):
{criteria}
</CURRENT_OBJECTIVE>

<ROE_GUARD_RAIL>
**Engagement**: {roe.engagement_name}
**Testing Window**: {roe.testing_window}

**IN SCOPE**:
{in_scope}

**OUT OF SCOPE** (DO NOT TOUCH):
{out_scope}

**Prohibited Actions**: {", ".join(roe.prohibited_actions[:3])}...
</ROE_GUARD_RAIL>

<THREAT_CONTEXT>
{opplan.threat_profile}
</THREAT_CONTEXT>
{findings_section}
<INSTRUCTIONS>
You are executing **one objective** in an autonomous red team loop.

1. Execute ONLY the objective above — do not work on other objectives
2. Check EVERY target against the RoE scope BEFORE scanning
3. Follow OPSEC notes strictly
4. Save ALL results to /workspace/ with clear filenames
5. When done, report:
   - Which acceptance criteria PASSED and which FAILED
   - Key findings discovered
   - Any blockers or issues
6. If ALL criteria pass, state: "OBJECTIVE PASSED"
7. If any criteria fail, state: "OBJECTIVE BLOCKED" with reasons
</INSTRUCTIONS>"""

    return prompt


def _create_loop_agent():
    """Create the Decepticon orchestrator agent for the ralph loop.

    The Decepticon agent handles strategic decisions internally via LLM:
    it reads the OPPLAN, selects the right sub-agent (recon/exploit/postexploit),
    and delegates via task(). This replaces the old Python if/elif phase mapping.
    """
    from decepticon.agents import create_decepticon_agent

    return create_decepticon_agent()


def _parse_iteration_result(output: str) -> tuple[bool, str]:
    """Parse the agent's output to determine if the objective passed.

    Returns (passed: bool, findings_summary: str).
    """
    text = output.strip()

    # Check for explicit pass/block signals
    passed = "OBJECTIVE PASSED" in text.upper()

    # Extract findings — everything the agent reported
    # Keep the full output as findings (will be truncated by findings manager)
    # Limit to last 2000 chars to avoid bloating findings.txt
    findings = text[-2000:] if len(text) > 2000 else text

    return passed, findings


class RalphLoop:
    """The autonomous red team execution loop.

    Usage:
        loop = RalphLoop(engagement_dir=Path("engagements/acme"))
        loop.run(renderer=my_renderer)
    """

    def __init__(
        self,
        engagement_dir: Path,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ):
        self.state = LoopState.load_or_create(engagement_dir, max_iterations)

    def run(self, renderer: Any) -> bool:
        """Run the full ralph loop until completion or max iterations.

        Args:
            renderer: UIRenderer for displaying agent output.

        Returns:
            True if all objectives completed, False if max iterations reached.
        """
        from decepticon.core.streaming import StreamingEngine

        self.state.active = True
        self.state.save_loop_state()

        log.info(
            "Ralph loop started: %s (%d max iterations)",
            self.state.opplan.engagement_name,
            self.state.max_iterations,
        )

        try:
            while self.state.iteration < self.state.max_iterations:
                # Reload documents from disk (may have been updated by previous iteration)
                self.state.reload()
                opplan = self.state.opplan

                # Check completion
                if opplan.is_complete():
                    log.info("All objectives completed!")
                    self.state.completed = True
                    self.state.save_loop_state()
                    return True

                # Pick next objective
                objective = opplan.next_objective()
                if objective is None:
                    log.info("No more pending objectives.")
                    self.state.completed = True
                    self.state.save_loop_state()
                    return True

                self.state.iteration += 1
                log.info(
                    "Iteration %d: %s — %s",
                    self.state.iteration,
                    objective.id,
                    objective.title,
                )

                # Mark objective as in-progress
                objective.status = ObjectiveStatus.IN_PROGRESS
                self.state.save_opplan()

                # Build the iteration prompt
                prompt = _build_iteration_prompt(self.state, objective)

                # Spawn Decepticon orchestrator — it delegates to sub-agents internally
                agent = _create_loop_agent()
                thread_id = f"ralph-{self.state.iteration}-{uuid.uuid4().hex[:6]}"
                config = {"configurable": {"thread_id": thread_id}}

                # Wire progress callback so long-running commands show UI
                # feedback without polluting the LLM context
                from decepticon.tools.bash.tool import get_sandbox

                sandbox = get_sandbox()
                if sandbox and hasattr(renderer, "on_tool_progress"):
                    sandbox.set_progress_callback(
                        lambda status, session, detail: renderer.on_tool_progress(
                            "bash",
                            session,
                            status,
                            detail,
                        )
                    )

                engine = StreamingEngine(agent=agent, renderer=renderer)

                # Execute
                output_parts: list[str] = []

                # Capture agent output for parsing
                original_on_ai = renderer.on_ai_message

                def _capture_ai(text: str) -> None:
                    output_parts.append(text)
                    original_on_ai(text)

                renderer.on_ai_message = _capture_ai  # type: ignore[assignment]

                try:
                    engine.run(prompt, config)
                except KeyboardInterrupt:
                    log.warning("Iteration %d interrupted by user", self.state.iteration)
                    objective.status = ObjectiveStatus.BLOCKED
                    objective.notes = "Interrupted by user"
                    self.state.save_opplan()
                    self.state.save_loop_state()
                    raise
                except Exception as e:
                    log.error("Iteration %d failed: %s", self.state.iteration, e)
                    objective.status = ObjectiveStatus.BLOCKED
                    objective.notes = f"Agent error: {e}"
                    self.state.save_opplan()
                    self.state.append_findings(objective, f"ERROR: {e}")
                    continue
                finally:
                    renderer.on_ai_message = original_on_ai  # type: ignore[assignment]

                # Parse result
                full_output = "\n".join(output_parts)
                passed, findings = _parse_iteration_result(full_output)

                # Update objective status
                if passed:
                    objective.status = ObjectiveStatus.PASSED
                    log.info("Objective %s PASSED", objective.id)
                else:
                    objective.status = ObjectiveStatus.BLOCKED
                    log.info("Objective %s BLOCKED", objective.id)

                # Persist state
                self.state.save_opplan()
                self.state.append_findings(objective, findings)
                self.state.save_loop_state()

            # Max iterations reached
            log.warning(
                "Max iterations (%d) reached. %s",
                self.state.max_iterations,
                self.state.opplan.progress_summary(),
            )
            return False

        finally:
            self.state.active = False
            self.state.save_loop_state()

    def status(self) -> str:
        """Return a human-readable status summary."""
        self.state.reload()
        opplan = self.state.opplan

        lines = [
            f"Engagement: {opplan.engagement_name}",
            f"Progress: {opplan.progress_summary()}",
            f"Iteration: {self.state.iteration} / {self.state.max_iterations}",
            f"Active: {self.state.active}",
            "",
            "Objectives:",
        ]

        for obj in opplan.objectives:
            icon = {
                ObjectiveStatus.PASSED: "[green]PASS[/green]",
                ObjectiveStatus.IN_PROGRESS: "[yellow]RUN[/yellow]",
                ObjectiveStatus.BLOCKED: "[red]BLOCK[/red]",
                ObjectiveStatus.PENDING: "[dim]PEND[/dim]",
                ObjectiveStatus.OUT_OF_SCOPE: "[dim]N/A[/dim]",
            }.get(obj.status, obj.status)
            lines.append(f"  {icon}  {obj.id}: {obj.title}")

        return "\n".join(lines)
