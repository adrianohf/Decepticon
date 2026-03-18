"""Decepticon configuration — defaults + environment variable overrides.

All LLM calls route through LiteLLM Docker proxy.
Model routing is defined in config/litellm.yaml.
Provider API keys are managed in .env (read by docker-compose).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


def _project_root() -> Path:
    """Project root (where docker-compose.yml lives)."""
    root = Path(__file__).resolve().parent.parent.parent
    if (root / "docker-compose.yml").exists():
        return root
    return Path.cwd()


class RoleModelConfig(BaseModel):
    """Per-role LLM settings.

    Model names must match litellm.yaml model_name aliases
    (e.g. recon-model, planning-model).
    """

    model: str
    temperature: float = 0.7


class LLMConfig(BaseModel):
    """LLM connection configuration (LiteLLM proxy)."""

    # LiteLLM proxy
    proxy_url: str = "http://localhost:4000"
    proxy_api_key: str = "sk-decepticon-master"

    # Provider (for display / .env key mapping only)
    provider: str = "anthropic"

    # Shared settings
    timeout: int = 120
    max_retries: int = 2

    roles: dict[str, RoleModelConfig] = Field(default_factory=lambda: {
        "recon": RoleModelConfig(model="recon-model", temperature=0.3),
        "planning": RoleModelConfig(model="planning-model", temperature=0.4),
        "exploit": RoleModelConfig(model="exploit-model", temperature=0.3),
        "postexploit": RoleModelConfig(model="postexploit-model", temperature=0.3),
        "decepticon": RoleModelConfig(model="decepticon-model", temperature=0.4),
    })


class DockerConfig(BaseModel):
    """Docker sandbox configuration."""

    sandbox_container_name: str = "decepticon-sandbox"
    sandbox_image: str = "decepticon-sandbox:latest"
    network: str = "decepticon-net"


class DecepticonConfig(BaseSettings):
    """Root configuration."""

    model_config = {"env_prefix": "DECEPTICON_", "env_nested_delimiter": "__"}

    debug: bool = False
    llm: LLMConfig = Field(default_factory=LLMConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)


def load_config() -> DecepticonConfig:
    """Load config from code defaults + environment variable overrides.

    Model routing is handled by config/litellm.yaml (not this config).
    """
    return DecepticonConfig()
