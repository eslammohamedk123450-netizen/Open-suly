from types import SimpleNamespace

from app import main


def test_opencode_runtime_stays_off_even_when_provisioner_settings_exist(monkeypatch):
    # Credentials and URL presence alone must never activate an agent engine.
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(
            opencode_enabled=False,
            hermes_agent_enabled=False,
            runtime_provisioner_url="https://runtime.example.test",
            runtime_provisioner_token=object(),
            runtime_provisioner_allowed_origins=["https://runtime.example.test"],
            runtime_provisioner_timeout_seconds=10,
        ),
    )

    main.configure_opencode_runtime()

    assert main.app.state.runtime_broker is None
    assert main.app.state.runtime_provider is None



def test_hermes_runtime_requires_complete_provisioner_configuration(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(
            opencode_enabled=False,
            hermes_agent_enabled=True,
            runtime_provisioner_url=None,
            runtime_provisioner_token=None,
            runtime_provisioner_allowed_origins=(),
            runtime_provisioner_timeout_seconds=10,
        ),
    )
    try:
        main.configure_opencode_runtime()
        assert False, "Hermes must not start without an isolated runtime provisioner"
    except RuntimeError as exc:
        assert "configuration is incomplete" in str(exc)


def test_hermes_runtime_configures_task_lease_provider(monkeypatch):
    class Token:
        def get_secret_value(self):
            return "runtime-provisioner-test-token"

    created = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            created.update(kwargs)
        def close(self):
            return None

    monkeypatch.setattr(main, "HTTPSRuntimeLeaseProvider", FakeProvider)
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(
            opencode_enabled=False,
            hermes_agent_enabled=True,
            runtime_provisioner_url="https://runtime-provisioner.internal",
            runtime_provisioner_token=Token(),
            runtime_provisioner_allowed_origins=["https://hermes-runtime.internal:8443"],
            runtime_provisioner_timeout_seconds=12,
        ),
    )

    main.configure_opencode_runtime()

    assert isinstance(main.app.state.runtime_provider, FakeProvider)
    assert created["base_url"] == "https://runtime-provisioner.internal"
    assert created["bearer_token"] == "runtime-provisioner-test-token"
    assert created["allowed_origins"] == frozenset({"https://hermes-runtime.internal:8443"})
    assert main.app.state.runtime_broker is not None
    main.close_opencode_runtime_provider()
