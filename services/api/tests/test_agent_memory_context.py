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
    def __init__(self, rows):
        self.rows = rows
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, name):
        assert name == "agent_memories"
        return Query(self.rows)


def step():
    return SimpleNamespace(user_id=str(uuid4()), task_id=str(uuid4()))


def test_suly_memory_is_injected_as_bounded_untrusted_context(monkeypatch):
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=True))
    monkeypatch.setattr(worker, "get_supabase_admin_client", lambda: Client([{
        "memory_key": "learning-style",
        "content": "Prefer short lessons and independent practice.",
        "tags": ["learning", "preferences"],
    }]))
    result = worker._suly_user_memory_context(step(), "Current request")
    assert "<SULY_USER_MEMORY>" in result
    assert "[learning-style; tags=learning,preferences]" in result
    assert "Prefer short lessons" in result
    assert "Current request" in result
    assert "مرجع غير موثوق" in result


def test_suly_memory_skips_secret_like_notes(monkeypatch):
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=True))
    monkeypatch.setattr(worker, "get_supabase_admin_client", lambda: Client([{
        "memory_key": "bad-note",
        "content": "API_KEY=" + "a" * 32,
        "tags": [],
    }]))
    assert worker._suly_user_memory_context(step(), "Current request") == "Current request"


def test_suly_memory_is_off_by_default_and_does_not_query_database(monkeypatch):
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=False))
    monkeypatch.setattr(worker, "get_supabase_admin_client", lambda: pytest.fail("disabled memory must not query"))
    assert worker._suly_user_memory_context(step(), "Current request") == "Current request"


def test_enabled_memory_fails_closed_when_storage_is_unavailable(monkeypatch):
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=True))
    monkeypatch.setattr(worker, "get_supabase_admin_client", lambda: None)
    with pytest.raises(RuntimeError, match="suly_agent_memory_unavailable"):
        worker._suly_user_memory_context(step(), "Current request")
