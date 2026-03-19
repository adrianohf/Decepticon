"""Decepticon configuration — defaults + environment variable overrides.

LLM model assignments are defined in decepticon.llm.models (LLMModelMapping).
This config handles infrastructure settings: proxy connection and Docker sandbox.
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


class LLMConfig(BaseModel):
    """LLM proxy connection configuration."""

    proxy_url: str = "http://localhost:4000"
    proxy_api_key: str = "sk-decepticon-master"
    timeout: int = 120
    max_retries: int = 2


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
    """Load config from code defaults + environment variable overrides."""
    return DecepticonConfig()
