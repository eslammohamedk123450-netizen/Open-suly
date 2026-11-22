from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import main
from app.main import app


client = TestClient(app)


def test_health_returns_liveness_without_credentials() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "suly-api",
        "version": "0.1.0",
    }


def test_readiness_reports_missing_supabase_configuration(monkeypatch) -> None:
    # نختبر نقص الإعدادات من دون أي اتصال خارجي أو بيانات سرية حقيقية.
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url=None,
            supabase_publishable_key=None,
            supabase_secret_key=None,
        ),
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "suly-api",
        "check": "configuration_only",
        "supabase": "missing_required_configuration",
        "missing": ["supabase_url", "supabase_publishable_key", "supabase_secret_key"],
    }


def test_readiness_accepts_configuration_without_claiming_network_health(monkeypatch) -> None:
    # وجود الإعدادات يرفع readiness التكويني فقط، ولا يدعي فحص Supabase فعليًا.
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key=SecretStr("public-test-placeholder"),
            supabase_secret_key=SecretStr("server-only-test-secret"),
        ),
    )

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "suly-api",
        "check": "configuration_only",
        "supabase": "configured",
        "missing": [],
    }
    assert "public-test-placeholder" not in response.text
    assert "server-only-test-secret" not in response.text


def test_cors_origin_validation_rejects_wildcards_and_http_in_production() -> None:
    from app.main import _validated_cors_origins

    import pytest

    with pytest.raises(RuntimeError):
        _validated_cors_origins(["*"], "production")
    with pytest.raises(RuntimeError):
        _validated_cors_origins(["http://client.example"], "production")


def test_cors_origin_validation_accepts_exact_https_origins() -> None:
    from app.main import _validated_cors_origins

    assert _validated_cors_origins(
        ["https://app.example.com", "https://admin.example.com/"], "production"
    ) == ["https://app.example.com", "https://admin.example.com"]
