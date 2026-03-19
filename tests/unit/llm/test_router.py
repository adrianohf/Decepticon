"""Unit tests for decepticon.llm.router"""

import pytest

from decepticon.llm.models import LLMModelMapping, ModelAssignment
from decepticon.llm.router import ModelRouter


class TestModelRouter:
    def setup_method(self):
        self.mapping = LLMModelMapping()
        self.router = ModelRouter(self.mapping)

    def test_resolve_returns_primary_model(self):
        model = self.router.resolve("recon")
        assert model == "claude-sonnet-4-20250514"

    def test_resolve_decepticon(self):
        model = self.router.resolve("decepticon")
        assert model == "claude-opus-4-20250514"

    def test_resolve_with_fallback_returns_chain(self):
        chain = self.router.resolve_with_fallback("recon")
        assert len(chain) == 2
        assert chain[0] == "claude-sonnet-4-20250514"
        assert chain[1] == "gpt-4o"

    def test_resolve_with_fallback_strategic(self):
        chain = self.router.resolve_with_fallback("exploit")
        assert len(chain) == 2
        assert chain[0] == "claude-opus-4-20250514"
        assert chain[1] == "claude-sonnet-4-20250514"

    def test_resolve_unknown_role_raises(self):
        with pytest.raises(KeyError, match="No model assignment"):
            self.router.resolve("nonexistent_role")

    def test_get_assignment_returns_full_config(self):
        assignment = self.router.get_assignment("recon")
        assert isinstance(assignment, ModelAssignment)
        assert assignment.primary == "claude-sonnet-4-20250514"
        assert assignment.temperature == 0.3
