"""LLM model definitions — per-role model assignments with fallbacks.

Each agent role gets a primary model and optional fallback. The assignments
reflect agent characteristics:

  - Strategic agents (orchestrator, planner, exploit): opus primary — needs
    strong reasoning and precision
  - Tactical agents (recon, postexploit): sonnet primary — tool-heavy
    workloads where cost/capability balance matters

Fallbacks activate automatically via ModelFallbackMiddleware when the
primary model fails (API outage, rate limit, missing key).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ProxyConfig(BaseModel):
    """LiteLLM proxy connection settings."""

    url: str = "http://localhost:4000"
    api_key: str = "sk-decepticon-master"
    timeout: int = 120
    max_retries: int = 2


class ModelAssignment(BaseModel):
    """Primary + fallback model for an agent role."""

    primary: str
    fallback: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v


class LLMModelMapping(BaseModel):
    """Role → model assignment mapping.

    Model names use LiteLLM format. The proxy routes to the correct provider.
    """

    # Strategic agents — opus primary (strong reasoning, document generation)
    decepticon: ModelAssignment = Field(
        default_factory=lambda: ModelAssignment(
            primary="claude-opus-4-20250514",
            fallback="claude-sonnet-4-20250514",
            temperature=0.4,
        )
    )
    planning: ModelAssignment = Field(
        default_factory=lambda: ModelAssignment(
            primary="claude-opus-4-20250514",
            fallback="claude-sonnet-4-20250514",
            temperature=0.4,
        )
    )
    exploit: ModelAssignment = Field(
        default_factory=lambda: ModelAssignment(
            primary="claude-opus-4-20250514",
            fallback="claude-sonnet-4-20250514",
            temperature=0.3,
        )
    )

    # Tactical agents — sonnet primary (tool-heavy, cost/capability balance)
    recon: ModelAssignment = Field(
        default_factory=lambda: ModelAssignment(
            primary="claude-sonnet-4-20250514",
            fallback="gpt-4o",
            temperature=0.3,
        )
    )
    postexploit: ModelAssignment = Field(
        default_factory=lambda: ModelAssignment(
            primary="claude-sonnet-4-20250514",
            fallback="gpt-4o",
            temperature=0.3,
        )
    )

    def get_assignment(self, role: str) -> ModelAssignment:
        """Get model assignment for a role.

        Raises KeyError if role not found.
        """
        if not hasattr(self, role):
            raise KeyError(f"No model assignment for role: {role}")
        return getattr(self, role)
