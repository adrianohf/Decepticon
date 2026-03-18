"""Recon Agent — autonomous reconnaissance and intelligence gathering.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely. This avoids unnecessary overhead from
TodoListMiddleware, SubAgentMiddleware, and BASE_AGENT_PROMPT that
create_deep_agent() forces.

Middleware stack (selected for recon):
  1. SkillsMiddleware — progressive disclosure of SKILL.md knowledge
  2. FilesystemMiddleware — ls/read/write/edit/glob/grep/execute tools
  3. SummarizationMiddleware — auto-compact when context budget exceeded
  4. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic
  5. PatchToolCallsMiddleware — repair dangling tool calls

Backend routing (CompositeBackend):
  /skills/*                → FilesystemBackend (host FS, read-only SKILL.md access)
  /workspace/.decepticon/* → FilesystemBackend (host FS, client-visible reports)
  default                  → DockerSandbox     (all file ops + bash execution in container)
"""

from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from decepticon.backends import DockerSandbox
from decepticon.core.config import load_config
from decepticon.core.types import AgentRole
from decepticon.llm import create_llm
from decepticon.tools.bash import bash
from decepticon.tools.bash.tool import set_sandbox

# Resolve paths relative to repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = Path(__file__).parent / "prompts" / "recon.md"


def _load_system_prompt() -> str:
    """Load the recon agent system prompt from the external markdown file."""
    return PROMPT_FILE.read_text(encoding="utf-8")


def create_recon_agent():
    """
    Initializes the Recon Agent using langchain create_agent() directly.

    Context engineering decisions:
      - CompositeBackend: /skills/* → host FS (read-only), default → Docker sandbox
      - /workspace/.decepticon/ → host FS (always <project_root>/.decepticon/)
      - InMemoryStore: cross-thread memory for persisting findings across sessions
      - Skills with progressive disclosure: only SKILL.md frontmatter loaded initially,
        full content loaded on-demand when the agent activates a skill
      - System prompt uses XML-tagged sections for clear attention boundaries
      - No TodoListMiddleware: opplan.json handles task tracking
      - No SubAgentMiddleware: Ralph loop handles agent orchestration
      - No BASE_AGENT_PROMPT: recon.md is the complete system prompt
    """
    config = load_config()

    llm = create_llm(AgentRole.RECON, config)

    # Build DockerSandbox and inject into bash tool
    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    set_sandbox(sandbox)

    system_prompt = _load_system_prompt()

    checkpointer = MemorySaver()
    store = InMemoryStore()

    # Route /skills/ to host filesystem; everything else goes into the container.
    # Route /workspace/.decepticon/ to <project_root>/.decepticon/ so write_file
    # saves reports directly to host FS (client-visible).
    report_dir = _REPO_ROOT / ".decepticon"
    report_dir.mkdir(parents=True, exist_ok=True)

    routes: dict[str, FilesystemBackend] = {
        "/skills/": FilesystemBackend(root_dir=_REPO_ROOT / "skills", virtual_mode=True),
        "/workspace/.decepticon/": FilesystemBackend(root_dir=report_dir),
    }

    backend = CompositeBackend(default=sandbox, routes=routes)

    # Assemble middleware stack — only what recon needs
    middleware = [
        SkillsMiddleware(backend=backend, sources=["/skills/recon/", "/skills/shared/"]),
        FilesystemMiddleware(backend=backend),
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
        store=store,
        name="recon",
    ).with_config({"recursion_limit": 40})

    return agent
