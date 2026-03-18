"""Decepticon Orchestrator — autonomous red team coordinator.

The top-level orchestration agent that coordinates the full kill chain.
It reads OPPLAN objectives, delegates to specialist sub-agents (recon,
exploit, postexploit, planner), and synthesizes results across phases.

Uses create_deep_agent() to get:
  - SubAgentMiddleware: task() tool for delegating to sub-agents
  - TodoListMiddleware: write_todos() for objective tracking
  - FilesystemMiddleware: file ops for reading/updating engagement docs
  - SkillsMiddleware: workflow skill for kill chain dependency graph
  - SummarizationMiddleware: auto-compact for long orchestration sessions

Sub-agents are passed as CompiledSubAgent, wrapping existing agent factories
(create_planner_agent, create_recon_agent, create_exploit_agent, create_postexploit_agent) so they
run with their full middleware stack and skill sets intact.
"""

from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.subagents import CompiledSubAgent
from langgraph.checkpoint.memory import MemorySaver

from decepticon.backends import DockerSandbox
from decepticon.core.config import load_config
from decepticon.core.subagent_streaming import StreamingRunnable
from decepticon.core.types import AgentRole
from decepticon.llm import create_llm
from decepticon.tools.bash import bash
from decepticon.tools.bash.tool import set_sandbox

# Resolve paths relative to repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = Path(__file__).parent / "prompts" / "decepticon.md"


def _load_system_prompt() -> str:
    """Load the Decepticon orchestrator system prompt."""
    return PROMPT_FILE.read_text(encoding="utf-8")


def create_decepticon_agent():
    """Initialize the Decepticon Orchestrator using create_deep_agent().

    This is the top-level agent that coordinates the full red team kill chain.
    It delegates actual offensive operations to specialist sub-agents while
    maintaining strategic oversight and engagement state.

    Architecture:
      - Decepticon (orchestrator) uses task() to delegate to sub-agents
      - Each sub-agent is a CompiledSubAgent wrapping an existing agent factory
      - Sub-agents retain their full middleware stack and skill sets
      - Decepticon has its own skills (/skills/decepticon/) + shared skills (/skills/shared/)

    Returns a compiled LangGraph agent ready for invocation.
    """
    config = load_config()

    llm = create_llm(AgentRole.DECEPTICON, config)

    # Build DockerSandbox — shared filesystem for all agents
    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    set_sandbox(sandbox)

    system_prompt = _load_system_prompt()

    checkpointer = MemorySaver()

    # Route /skills/ to host filesystem; everything else goes into the container
    backend = CompositeBackend(
        default=sandbox,
        routes={"/skills/": FilesystemBackend(root_dir=_REPO_ROOT / "skills", virtual_mode=True)},
    )

    # Build sub-agents from existing agent factories
    # Each sub-agent retains its full middleware stack and skill sets
    from decepticon.agents.exploit import create_exploit_agent
    from decepticon.agents.planner import create_planner_agent
    from decepticon.agents.postexploit import create_postexploit_agent
    from decepticon.agents.recon import create_recon_agent

    # Build sub-agents with StreamingRunnable wrappers.
    # StreamingRunnable intercepts invoke() → uses stream() internally,
    # emitting tool calls, results, and AI messages to the CLI renderer
    # in real time. Without this, task() runs silently and only returns
    # the final result (deepagents default behavior).
    subagents = [
        CompiledSubAgent(
            name="planner",
            description=(
                "Planning agent. Generates engagement document bundles: RoE, CONOPS, OPPLAN, "
                "Deconfliction Plan. Use when engagement documents are missing or need updating. "
                "Interviews the user, produces JSON documents, validates against schemas. "
                "Saves results to /workspace/"
            ),
            runnable=StreamingRunnable(create_planner_agent(), "planner"),
        ),
        CompiledSubAgent(
            name="recon",
            description=(
                "Reconnaissance agent. Passive/active recon, OSINT, web/cloud recon. "
                "Use for: subdomain enumeration, port scanning, service detection, "
                "vulnerability scanning, OSINT gathering. "
                "Saves results to /workspace/recon/"
            ),
            runnable=StreamingRunnable(create_recon_agent(), "recon"),
        ),
        CompiledSubAgent(
            name="exploit",
            description=(
                "Exploitation agent. Initial access via web/AD attacks. "
                "Use for: SQLi, SSTI, Kerberoasting, ADCS abuse, credential attacks. "
                "Use after recon identifies attack surface. "
                "Saves results to /workspace/exploit/"
            ),
            runnable=StreamingRunnable(create_exploit_agent(), "exploit"),
        ),
        CompiledSubAgent(
            name="postexploit",
            description=(
                "Post-exploitation agent. Credential access, privilege escalation, "
                "lateral movement, C2 management. "
                "Use after initial foothold is established. "
                "Saves results to /workspace/post-exploit/"
            ),
            runnable=StreamingRunnable(create_postexploit_agent(), "postexploit"),
        ),
    ]

    agent = create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
        tools=[bash],  # For reading/writing engagement docs directly
        subagents=subagents,
        skills=["/skills/decepticon/", "/skills/shared/"],
        backend=backend,
        checkpointer=checkpointer,
    )

    # Orchestrator needs a higher recursion budget than sub-agents (40).
    # Each delegation cycle = AI think + task() call + result processing.
    # With todo tracking, skill loading, and multiple delegations, 40 is
    # easily exhausted. Sub-agents have their own separate recursion budgets.
    return agent.with_config({"recursion_limit": 200})
