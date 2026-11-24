from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.worker_runtime as worker


class Query:
    def __init__(self, rows):
        self.rows = rows
    def select(self, _columns): return self
    def eq(self, *_args): return self
    def order(self, *_args, **_kwargs): return self
    def limit(self, _value): return self
    def execute(self): return SimpleNamespace(data=self.rows)


class Client:
    def table(self, _name):
        raise AssertionError("the injected store should serve this focused unit test")


def step():
    return SimpleNamespace(user_id=str(uuid4()), task_id=str(uuid4()))


def test_suly_memory_is_injected_as_bounded_untrusted_context(monkeypatch):
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=True))
    monkeypatch.setattr(worker, "get_supabase_admin_client", lambda: Client())

    class MemoryStore:
        def context_for_task(self, **kwargs):
            assert kwargs["project_id"] is None
            assert kwargs["conversation_id"] is None
            return [{
                "scope": "user",
                "memory_key": "learning-style",
                "content": "Prefer short lessons and independent practice.",
            }]

    result = worker._suly_user_memory_context(
        step(), "Current request",
        task_scope={"project_id": None, "conversation_id": None},
        store=MemoryStore(),
    )
    assert "<SULY_APPROVED_MEMORY>" in result
    assert "[user:learning-style]" in result
    assert "Prefer short lessons" in result
    assert "Current request" in result
    assert "غير موثوقة" in result

def test_suly_memory_context_has_shared_character_budget(monkeypatch):
    import app.worker_runtime as runtime_module

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=True))
    class Client:
        def table(self, _name): return self
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: Client())
    requested = []
    class MemoryStore:
        def context_for_task(self, **kwargs):
            requested.append(kwargs["max_bytes"])
            return [
                {"scope": "user", "memory_key": f"preference-{i}", "content": "m" * 1_500}
                for i in range(5)
            ]

    prompt = "task request"
    result = runtime_module._suly_user_memory_context(
        step(), prompt,
        task_scope={"project_id": None, "conversation_id": None},
        store=MemoryStore(),
    )

    assert requested == [runtime_module._HERMES_MEMORY_FETCH_MAX_BYTES]
    assert result.startswith("ملاحظات ذاكرة SULY")
    assert result.endswith(prompt)
    assert len(result) <= runtime_module._HERMES_CONTEXT_CHAR_BUDGET
    assert len(result) - len(prompt) <= runtime_module._HERMES_MEMORY_CONTEXT_MAX_CHARS + 400



def test_suly_memory_skips_secret_like_notes(monkeypatch):
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=True))
    monkeypatch.setattr(worker, "get_supabase_admin_client", lambda: Client())

    class MemoryStore:
        def context_for_task(self, **_kwargs):
            return [{
                "scope": "user",
                "memory_key": "bad-note",
                "content": "API_KEY=" + "a" * 32,
            }]

    assert worker._suly_user_memory_context(
        step(), "Current request",
        task_scope={"project_id": None, "conversation_id": None},
        store=MemoryStore(),
    ) == "Current request"


def test_suly_memory_is_off_by_default_and_does_not_query_database(monkeypatch):
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=False))
    monkeypatch.setattr(worker, "get_supabase_admin_client", lambda: pytest.fail("disabled memory must not query"))
    assert worker._suly_user_memory_context(step(), "Current request") == "Current request"


def test_enabled_memory_fails_closed_when_storage_is_unavailable(monkeypatch):
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=True))
    monkeypatch.setattr(worker, "get_supabase_admin_client", lambda: None)
    with pytest.raises(RuntimeError, match="suly_agent_memory_unavailable"):
        worker._suly_user_memory_context(step(), "Current request")
