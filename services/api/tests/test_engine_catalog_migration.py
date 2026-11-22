from __future__ import annotations

from pathlib import Path


def _migration_text() -> str:
    repository_root = Path(__file__).resolve().parents[3]
    path = repository_root / "supabase" / "migrations" / "20261122030500_universal_engine_runtime_catalog.sql"
    return path.read_text(encoding="utf-8")


def test_engine_catalog_migration_is_server_only_and_provenance_pinned():
    sql = _migration_text()
    assert "create table if not exists public.engine_runtime_catalog" in sql
    assert "alter table public.engine_runtime_catalog enable row level security" in sql
    assert "revoke all on table public.engine_runtime_catalog from public, anon, authenticated" in sql
    assert "grant all on table public.engine_runtime_catalog to service_role" in sql
    assert "upstream_repository" in sql
    assert "upstream_revision" in sql
    assert "license_id" in sql
    assert "valid_engine_capabilities" in sql


def test_engine_collaboration_rpcs_use_catalog_not_a_two_engine_allowlist():
    sql = _migration_text()
    create_start = sql.index("create or replace function public.create_engine_collaboration_handoff")
    approve_start = sql.index("create or replace function public.approve_engine_collaboration_handoff")
    create_sql = sql[create_start:approve_start]
    approve_sql = sql[approve_start:]

    assert "v_target_catalog.task_operation" in approve_sql
    assert "p_target_engine not in ('hermes-agent','opencode')" not in create_sql
    assert "v_run.engine_id not in ('hermes-agent','opencode')" not in create_sql
    assert "v_handoff.target_engine = 'opencode'" not in approve_sql
    assert "v_handoff.target_engine = 'hermes-agent'" not in approve_sql
    assert "handoff_context" in create_sql
    assert "handoff_context" in approve_sql
