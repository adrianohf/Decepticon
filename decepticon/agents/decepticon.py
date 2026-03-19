"""Decepticon Orchestrator — autonomous red team coordinator.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely. The orchestrator coordinates the full kill chain
by delegating to specialist sub-agents (recon, exploit, postexploit, planner).

Middleware stack (selected for orchestration):
  1. SkillsMiddleware — progressive disclosure of SKILL.md knowledge
  2. FilesystemMiddleware — file ops for reading/updating engagement docs
  3. SubAgentMiddleware — task() tool for delegating to sub-agents
  4. TodoListMiddleware — write_todos() for objective tracking
  5. SummarizationMiddleware — auto-compact for long orchestration sessions
  6. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic
  7. PatchToolCallsMiddleware — repair dangling tool calls

Sub-agents are passed as CompiledSubAgent, wrapping existing agent factories
(create_planner_agent, create_recon_agent, create_exploit_agent,
create_postexploit_agent) so they run with their full middleware stack and
skill sets intact.
"""

from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from deepagents.middleware.subagents import CompiledSubAgent, SubAgentMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
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
    """Initialize the Decepticon Orchestrator using create_agent() directly.

    Context engineering decisions:
      - Explicit middleware stack instead of create_deep_agent() defaults
      - SubAgentMiddleware: task() tool for delegating to specialist sub-agents
      - TodoListMiddleware: write_todos() for objective tracking during orchestration
      - No BASE_AGENT_PROMPT: decepticon.md is the complete system prompt
      - CompositeBackend: /skills/* → host FS (read-only), default → Docker sandbox

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

    # Assemble middleware stack — orchestrator needs SubAgentMiddleware + TodoListMiddleware
    # on top of the standard stack used by specialist agents
    middleware = [
        SkillsMiddleware(backend=backend, sources=["/skills/decepticon/", "/skills/shared/"]),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(subagents=subagents),
        TodoListMiddleware(),
        create_summarization_middleware(llm, backend),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        PatchToolCallsMiddleware(),
    ]

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=[bash],
        middleware=middleware,
        checkpointer=checkpointer,
        name="decepticon",
    )

    # Orchestrator needs a higher recursion budget than sub-agents (40).
    # Each delegation cycle = AI think + task() call + result processing.
    # With todo tracking, skill loading, and multiple delegations, 40 is
    # easily exhausted. Sub-agents have their own separate recursion budgets.
    return agent.with_config({"recursion_limit": 200})
