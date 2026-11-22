from types import SimpleNamespace

from app.routers import chat as chat_module


class _MemoryQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args): return self
    def eq(self, *_args): return self
    def order(self, *_args, **_kwargs): return self
    def limit(self, _value): return self
    def execute(self): return SimpleNamespace(data=self.rows)


class _MemoryAdmin:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, name):
        assert name == "agent_memories"
        return _MemoryQuery(self.rows)


def test_chat_memory_combines_user_notes_and_scoped_memory(monkeypatch):
    from app.core.config import Settings
    import app.services.hermes_state_store as state_store

    monkeypatch.setattr(chat_module, "get_settings", lambda: Settings(agent_memory_enabled=True))
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: _MemoryAdmin([
        {"memory_key": "reply-language", "content": "Arabic"},
        {"memory_key": "secret-note", "content": "API_KEY=" + "x" * 32},
    ]))

    class FakeHermesStateStore:
        def __init__(self, _admin): pass
        def context_for_task(self, **kwargs):
            assert kwargs["user_id"] == "owner-a"
            assert kwargs["project_id"] == "project-a"
            assert kwargs["conversation_id"] == "conversation-a"
            return [{
                "scope": "project",
                "memory_key": "project-style",
                "content": {"format": "short steps"},
            }]

    monkeypatch.setattr(state_store, "HermesStateStore", FakeHermesStateStore)
    result = chat_module._load_chat_memory_context("owner-a", "project-a", "conversation-a")

    assert "[user:reply-language] Arabic" in result
    assert "[project:project-style]" in result
    assert "short steps" in result
    assert "secret-note" not in result
    assert "API_KEY" not in result


def test_chat_memory_is_disabled_without_database_access(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setattr(chat_module, "get_settings", lambda: Settings(agent_memory_enabled=False))
    monkeypatch.setattr(
        chat_module,
        "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("disabled memory must not access storage")),
    )
    assert chat_module._load_chat_memory_context("owner-a", None, "conversation-a") == ""
