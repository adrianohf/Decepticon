"""LLM Factory — creates ChatModel instances via LiteLLM proxy.

All LLM calls route through the LiteLLM Docker proxy for provider abstraction.
Provider API keys are configured in .env / docker-compose.yml.

Architecture:
    LLMFactory(proxy, mapping)
      → get_model("recon")  → ChatOpenAI(model="claude-sonnet-4-20250514")
      → get_fallback_models("recon") → [ChatOpenAI(model="gpt-4o")]
                                         ↓
                        LiteLLM proxy → Anthropic/OpenAI/etc.
"""

from __future__ import annotations

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from decepticon.core.logging import get_logger
from decepticon.llm.models import LLMModelMapping, ProxyConfig
from decepticon.llm.router import ModelRouter

log = get_logger("llm.factory")


class LLMFactory:
    """Creates and caches LangChain ChatModel instances per agent role.

    Routes all models through LiteLLM proxy. Supports primary + fallback
    model resolution via ModelRouter.
    """

    def __init__(
        self,
        proxy: ProxyConfig | None = None,
        mapping: LLMModelMapping | None = None,
    ):
        self._proxy = proxy or ProxyConfig()
        self._mapping = mapping or LLMModelMapping()
        self._router = ModelRouter(self._mapping)
        self._cache: dict[str, BaseChatModel] = {}

    @property
    def proxy_url(self) -> str:
        return self._proxy.url

    @property
    def router(self) -> ModelRouter:
        return self._router

    def get_model(self, role: str) -> BaseChatModel:
        """Get the primary ChatModel for a role. Cached per role."""
        if role in self._cache:
            return self._cache[role]

        assignment = self._router.get_assignment(role)
        log.info(
            "Creating LLM for role '%s' → model '%s' via %s",
            role,
            assignment.primary,
            self._proxy.url,
        )

        model = self._create_chat_model(assignment.primary, assignment.temperature)
        self._cache[role] = model
        return model

    def get_fallback_models(self, role: str) -> list[BaseChatModel]:
        """Get fallback ChatModel instances for a role. Empty if no fallback."""
        assignment = self._router.get_assignment(role)
        if not assignment.fallback:
            return []

        log.info(
            "Creating fallback LLM for role '%s' → model '%s'",
            role,
            assignment.fallback,
        )
        return [self._create_chat_model(assignment.fallback, assignment.temperature)]

    def _create_chat_model(self, model: str, temperature: float) -> BaseChatModel:
        """Create a ChatOpenAI instance routed through LiteLLM proxy."""
        return ChatOpenAI(
            model=model,
            base_url=self._proxy.url,
            api_key=self._proxy.api_key,
            temperature=temperature,
            timeout=self._proxy.timeout,
            max_retries=self._proxy.max_retries,
        )

    async def health_check(self) -> bool:
        """Check if the LiteLLM proxy is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._proxy.url}/health")
                return resp.status_code == 200
        except Exception:
            return False


def create_llm(role: str, config: object | None = None) -> BaseChatModel:
    """Convenience function — creates primary model for a role.

    Backward-compatible wrapper around LLMFactory.
    The `config` parameter is accepted but ignored (kept for call-site compat).
    """
    factory = LLMFactory()
    role_str = role.value if hasattr(role, "value") else role
    return factory.get_model(role_str)
