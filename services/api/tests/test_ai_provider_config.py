from pydantic import SecretStr

from app.core.config import Settings
from app.services import ai_provider_config


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRpc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return FakeResponse(self.data)


class FakeAdmin:
    def __init__(self, config):
        self.config = config
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return FakeRpc(self.config)


def test_vault_config_is_loaded_as_server_secret(monkeypatch):
    admin = FakeAdmin({
        "provider": "openai-compatible",
        "base_url": "https://provider.example/v1",
        "model": "test-model",
        "api_key": "test-only-not-a-real-key",
    })
    monkeypatch.setattr(ai_provider_config, "get_settings", lambda: Settings(ai_timeout_seconds=13, ai_max_output_tokens=600))

    config = ai_provider_config.read_ai_provider_config(admin)
    settings = ai_provider_config.ai_settings_from_config(config)

    assert admin.calls[0][0] == "suly_ai_provider_config_get"
    assert isinstance(config["api_key"], SecretStr)
    assert settings.ai_api_key.get_secret_value() == "test-only-not-a-real-key"
    assert settings.ai_provider == "openai-compatible"
    assert settings.ai_timeout_seconds == 13
    assert settings.ai_max_output_tokens == 600


def test_store_uses_only_restricted_set_rpc():
    admin = FakeAdmin(None)
    ai_provider_config.store_ai_provider_config(
        admin,
        base_url="https://provider.example/v1",
        model="test-model",
        api_key="test-only-not-a-real-key",
    )

    name, params = admin.calls[0]
    assert name == "suly_ai_provider_config_set"
    assert params["p_config"]["provider"] == "openai-compatible"
    assert params["p_config"]["api_key"] == "test-only-not-a-real-key"



def test_clear_uses_only_the_restricted_vault_rpc():
    admin = FakeAdmin({"provider": "openai-compatible"})
    ai_provider_config.clear_ai_provider_config(admin)
    assert admin.calls == [("suly_ai_provider_config_clear", {})]


def test_clear_rpc_failure_is_sanitized():
    class FailingAdmin:
        def rpc(self, *_args, **_kwargs):
            raise RuntimeError("private database failure")

    try:
        ai_provider_config.clear_ai_provider_config(FailingAdmin())
    except ai_provider_config.AIProviderConfigurationUnavailable as exc:
        assert "private database failure" not in str(exc)
    else:
        raise AssertionError("Vault clear failure must be surfaced as a safe configuration error")
