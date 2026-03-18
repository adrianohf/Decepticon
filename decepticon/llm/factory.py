"""LLM Factory — creates ChatModel instances via LiteLLM proxy.

All LLM calls route through the LiteLLM Docker proxy for provider abstraction.
Provider API keys are configured in .env / docker-compose.yml.

Architecture:
    Agent → create_llm("recon", config)
          → ChatOpenAI(base_url="http://localhost:4000", model="recon-model")
          → LiteLLM → Anthropic/OpenAI/Ollama/etc.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from decepticon.core.config import DecepticonConfig
from decepticon.core.exceptions import LLMError
from decepticon.core.logging import get_logger
from decepticon.core.types import AgentRole

log = get_logger("llm.factory")


def _get_role_config(role: AgentRole | str, config: DecepticonConfig):
    """Resolve role string to RoleModelConfig."""
    role_str = role.value if isinstance(role, AgentRole) else role
    role_cfg = config.llm.roles.get(role_str)
    if role_cfg is None:
        raise LLMError(f"No model configured for role: {role_str}")
    return role_str, role_cfg


def create_llm(role: AgentRole | str, config: DecepticonConfig) -> BaseChatModel:
    """Create a LangChain ChatModel for the given agent role.

    Routes through LiteLLM Docker proxy. Model names must match
    aliases defined in config/litellm.yaml (e.g. recon-model, planning-model).

    Args:
        role: Agent role (AgentRole enum or string matching config key).
        config: Decepticon configuration.

    Returns:
        LangChain BaseChatModel instance.
    """
    _, role_cfg = _get_role_config(role, config)
    llm = config.llm

    log.info("Creating LLM for role '%s' → model '%s' via %s", role, role_cfg.model, llm.proxy_url)

    return ChatOpenAI(
        model=role_cfg.model,
        base_url=llm.proxy_url,
        api_key=llm.proxy_api_key,
        temperature=role_cfg.temperature,
        timeout=llm.timeout,
        max_retries=llm.max_retries,
    )
