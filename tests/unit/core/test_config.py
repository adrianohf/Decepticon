"""Unit tests for decepticon.core.config"""

from decepticon.core.config import DecepticonConfig, load_config


class TestDecepticonConfig:
    def test_default_values(self):
        config = DecepticonConfig()
        assert config.debug is False

    def test_llm_defaults(self):
        config = DecepticonConfig()
        assert config.llm.proxy_url == "http://localhost:4000"
        assert "recon" in config.llm.roles
        assert "planning" in config.llm.roles

    def test_role_model_aliases(self):
        config = DecepticonConfig()
        assert config.llm.roles["recon"].model == "recon-model"
        assert config.llm.roles["planning"].model == "planning-model"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_DEBUG", "true")
        config = DecepticonConfig()
        assert config.debug is True


class TestLoadConfig:
    def test_returns_defaults(self):
        config = load_config()
        assert config.llm.proxy_url == "http://localhost:4000"
        assert config.llm.roles["recon"].temperature == 0.3
