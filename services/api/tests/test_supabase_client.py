from types import SimpleNamespace
from unittest.mock import Mock

from pydantic import SecretStr

from app.core import supabase as supabase_module


def test_client_uses_publishable_key(monkeypatch) -> None:
    fake_client = SimpleNamespace(postgrest=Mock())
    create_client = Mock(return_value=fake_client)
    monkeypatch.setattr(supabase_module, "create_client", create_client)
    monkeypatch.setattr(
        supabase_module,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key=SecretStr("sb_publishable_test"),
        ),
    )

    result = supabase_module.get_supabase_client()

    assert result is fake_client
    create_client.assert_called_once_with(
        "https://example.supabase.co",
        "sb_publishable_test",
    )
    fake_client.postgrest.auth.assert_not_called()


def test_client_applies_request_access_token(monkeypatch) -> None:
    fake_client = SimpleNamespace(postgrest=Mock())
    monkeypatch.setattr(
        supabase_module,
        "create_client",
        Mock(return_value=fake_client),
    )
    monkeypatch.setattr(
        supabase_module,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key=SecretStr("sb_publishable_test"),
        ),
    )

    result = supabase_module.get_supabase_client("verified-user-jwt")

    assert result is fake_client
    fake_client.postgrest.auth.assert_called_once_with("verified-user-jwt")


def test_client_is_unavailable_without_configuration(monkeypatch) -> None:
    create_client = Mock()
    monkeypatch.setattr(supabase_module, "create_client", create_client)
    monkeypatch.setattr(
        supabase_module,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url=None,
            supabase_publishable_key=None,
        ),
    )

    assert supabase_module.get_supabase_client() is None
    create_client.assert_not_called()
