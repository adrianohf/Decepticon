"""Unit tests for decepticon.auth module"""

import json
import time
from pathlib import Path

import pytest

from decepticon.auth.manager import AuthManager
from decepticon.auth.storage import CredentialStore
from decepticon.auth.types import ApiKeyCredential, OAuthCredential


class TestCredentialTypes:
    def test_api_key_not_expired(self):
        cred = ApiKeyCredential(provider="openai", key="sk-test123")
        assert cred.is_expired is False
        assert cred.type == "api_key"

    def test_oauth_not_expired(self):
        cred = OAuthCredential(
            provider="anthropic",
            access_token="acc-123",
            refresh_token="ref-456",
            expires_at=time.time() + 3600,
        )
        assert cred.is_expired is False
        assert cred.expires_in_seconds > 0

    def test_oauth_expired(self):
        cred = OAuthCredential(
            provider="anthropic",
            access_token="acc-123",
            refresh_token="ref-456",
            expires_at=time.time() - 100,
        )
        assert cred.is_expired is True
        assert cred.expires_in_seconds == 0


class TestCredentialStore:
    def test_read_empty(self, tmp_path: Path):
        store = CredentialStore(auth_file=tmp_path / "auth.json")
        assert store.read() == {}

    def test_set_and_get_api_key(self, tmp_path: Path):
        store = CredentialStore(auth_file=tmp_path / "auth.json")
        cred = ApiKeyCredential(provider="openai", key="sk-test")

        store.set("openai", cred)
        result = store.get("openai")

        assert result is not None
        assert isinstance(result, ApiKeyCredential)
        assert result.key == "sk-test"

    def test_set_and_get_oauth(self, tmp_path: Path):
        store = CredentialStore(auth_file=tmp_path / "auth.json")
        cred = OAuthCredential(
            provider="anthropic",
            access_token="acc-123",
            refresh_token="ref-456",
            expires_at=time.time() + 3600,
        )

        store.set("anthropic", cred)
        result = store.get("anthropic")

        assert result is not None
        assert isinstance(result, OAuthCredential)
        assert result.access_token == "acc-123"

    def test_remove(self, tmp_path: Path):
        store = CredentialStore(auth_file=tmp_path / "auth.json")
        store.set("openai", ApiKeyCredential(provider="openai", key="sk-test"))
        store.remove("openai")
        assert store.get("openai") is None

    def test_list_providers(self, tmp_path: Path):
        store = CredentialStore(auth_file=tmp_path / "auth.json")
        store.set("openai", ApiKeyCredential(provider="openai", key="k1"))
        store.set("anthropic", ApiKeyCredential(provider="anthropic", key="k2"))

        providers = store.list_providers()
        assert "openai" in providers
        assert "anthropic" in providers

    def test_persistence(self, tmp_path: Path):
        auth_file = tmp_path / "auth.json"
        store1 = CredentialStore(auth_file=auth_file)
        store1.set("openai", ApiKeyCredential(provider="openai", key="sk-persist"))

        # New store instance reads same file
        store2 = CredentialStore(auth_file=auth_file)
        result = store2.get("openai")
        assert result is not None
        assert isinstance(result, ApiKeyCredential)
        assert result.key == "sk-persist"


class TestAuthManager:
    def test_available_providers(self):
        manager = AuthManager()
        providers = manager.available_providers
        assert "anthropic" in providers
        assert "openai" in providers
        assert "github-copilot" in providers

    def test_get_provider(self):
        manager = AuthManager()
        provider = manager.get_provider("anthropic")
        assert provider.id == "anthropic"

    def test_get_unknown_provider_raises(self):
        manager = AuthManager()
        with pytest.raises(KeyError, match="Unknown provider"):
            manager.get_provider("nonexistent")

    def test_get_api_key(self, tmp_path: Path):
        import asyncio

        store = CredentialStore(auth_file=tmp_path / "auth.json")
        manager = AuthManager(store=store)

        store.set("anthropic", ApiKeyCredential(provider="anthropic", key="sk-test-key"))
        key = asyncio.run(manager.get_api_key("anthropic"))
        assert key == "sk-test-key"

    def test_logout(self, tmp_path: Path):
        store = CredentialStore(auth_file=tmp_path / "auth.json")
        manager = AuthManager(store=store)

        store.set("anthropic", ApiKeyCredential(provider="anthropic", key="sk-test"))
        manager.logout("anthropic")
        assert store.get("anthropic") is None

    def test_get_status(self, tmp_path: Path):
        store = CredentialStore(auth_file=tmp_path / "auth.json")
        manager = AuthManager(store=store)

        store.set("openai", ApiKeyCredential(provider="openai", key="sk-test"))
        status = manager.get_status()
        assert len(status) == 1
        assert status[0]["provider"] == "openai"
        assert status[0]["type"] == "api_key"
        assert status[0]["is_expired"] is False
