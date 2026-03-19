"""Unit tests for decepticon.llm.models"""

import pytest

from decepticon.llm.models import LLMModelMapping, ModelAssignment, ProxyConfig


class TestModelAssignment:
    def test_defaults(self):
        assignment = ModelAssignment(primary="test-model")
        assert assignment.primary == "test-model"
        assert assignment.fallback is None
        assert assignment.temperature == 0.7
        assert assignment.max_tokens is None

    def test_with_fallback(self):
        assignment = ModelAssignment(
            primary="model-a",
            fallback="model-b",
            temperature=0.3,
        )
        assert assignment.fallback == "model-b"
        assert assignment.temperature == 0.3

    def test_temperature_bounds(self):
        with pytest.raises(Exception):
            ModelAssignment(primary="x", temperature=3.0)
        with pytest.raises(Exception):
            ModelAssignment(primary="x", temperature=-0.1)


class TestLLMModelMapping:
    def test_default_roles_exist(self):
        mapping = LLMModelMapping()
        assert mapping.decepticon is not None
        assert mapping.recon is not None
        assert mapping.exploit is not None
        assert mapping.planning is not None
        assert mapping.postexploit is not None

    def test_get_assignment_valid(self):
        mapping = LLMModelMapping()
        assignment = mapping.get_assignment("recon")
        assert assignment.primary == "claude-sonnet-4-20250514"

    def test_get_assignment_invalid(self):
        mapping = LLMModelMapping()
        with pytest.raises(KeyError):
            mapping.get_assignment("nonexistent")

    def test_strategic_agents_use_opus(self):
        mapping = LLMModelMapping()
        for role in ("decepticon", "planning", "exploit"):
            assert "opus" in mapping.get_assignment(role).primary

    def test_tactical_agents_use_sonnet(self):
        mapping = LLMModelMapping()
        for role in ("recon", "postexploit"):
            assert "sonnet" in mapping.get_assignment(role).primary


class TestProxyConfig:
    def test_defaults(self):
        config = ProxyConfig()
        assert config.url == "http://localhost:4000"
        assert config.timeout == 120
        assert config.max_retries == 2
