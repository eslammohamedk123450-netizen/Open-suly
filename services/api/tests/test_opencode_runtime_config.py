from types import SimpleNamespace

from app import main


def test_opencode_runtime_stays_off_even_when_provisioner_settings_exist(monkeypatch):
    # Credentials and URL presence alone must never activate an agent engine.
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(
            opencode_enabled=False,
            runtime_provisioner_url="https://runtime.example.test",
            runtime_provisioner_token=object(),
            runtime_provisioner_allowed_origins=["https://runtime.example.test"],
            runtime_provisioner_timeout_seconds=10,
        ),
    )

    main.configure_opencode_runtime()

    assert main.app.state.runtime_broker is None
    assert main.app.state.runtime_provider is None
