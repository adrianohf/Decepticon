"""Unit tests for decepticon.core.exceptions"""

import pytest

from decepticon.core.exceptions import (
    AgentError,
    ConfigError,
    DecepticonError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    SandboxError,
    ToolError,
)


class TestExceptionHierarchy:
    def test_base_exception(self):
        err = DecepticonError("test error")
        assert "test error" in str(err)
        assert err.message == "test error"

    def test_config_error_is_decepticon_error(self):
        assert issubclass(ConfigError, DecepticonError)

    def test_llm_error_hierarchy(self):
        assert issubclass(LLMError, DecepticonError)
        assert issubclass(LLMConnectionError, LLMError)
        assert issubclass(LLMRateLimitError, LLMError)

    def test_all_errors_are_decepticon_errors(self):
        error_classes = [
            ConfigError, LLMError, LLMConnectionError,
            LLMRateLimitError, AgentError, ToolError, SandboxError,
        ]
        for cls in error_classes:
            assert issubclass(cls, DecepticonError)
            err = cls("test")
            assert isinstance(err, DecepticonError)

    def test_can_catch_with_base(self):
        with pytest.raises(DecepticonError):
            raise LLMConnectionError("connection failed")
