from __future__ import annotations

from pathlib import Path


def _migration() -> str:
    root = Path(__file__).resolve().parents[3]
    return (root / "supabase" / "migrations" / "20261122050000_hermes_delegation_outbox.sql").read_text(encoding="utf-8")


def test_outbox_is_server_only_and_durable():
    sql = _migration()
    assert "create table if not exists public.hermes_delegation_outbox" in sql
    assert "unique references public.task_steps(id)" in sql
    assert "enable row level security" in sql
    assert "revoke all on table public.hermes_delegation_outbox from public,anon,authenticated" in sql
    assert "grant all on table public.hermes_delegation_outbox to service_role" in sql


def test_completed_hermes_step_enqueues_only_verified_plan_for_successful_run():
    sql = _migration()
    assert "create or replace function public.enqueue_completed_hermes_delegation_plan()" in sql
    assert "new.input->>'operation' <> 'hermes.agent.turn'" in sql
    assert "new.status <> 'completed'" in sql
    assert "engine_id = 'hermes-agent'" in sql
    assert "status = 'succeeded'" in sql
    assert "on conflict (step_id) do nothing" in sql
    assert "hermes_delegation_outbox_idempotency_conflict" in sql


def test_outbox_claim_and_completion_are_lease_guarded_and_retryable():
    sql = _migration()
    assert "for update skip locked" in sql
    assert "lease_expires_at < now()" in sql
    assert "p_lease_token" in sql
    assert "lease_expires_at > now()" in sql
    assert "available_at = now() + make_interval" in sql
    assert "attempt_count >= 8" in sql
