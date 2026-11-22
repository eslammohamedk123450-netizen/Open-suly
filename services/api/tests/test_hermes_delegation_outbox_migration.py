from __future__ import annotations

from pathlib import Path
import re


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
    assert "new.input->>'operation' is distinct from 'hermes.agent.turn'" in sql
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
    assert "cancel_hermes_delegation_outbox_on_parent_cancel" in sql
    assert "parent_task_cancelled" in sql


def _collaboration_lifecycle_migration() -> str:
    root = Path(__file__).resolve().parents[3]
    return (root / "supabase" / "migrations" / "20261122060000_engine_collaboration_lifecycle_guards.sql").read_text(encoding="utf-8")


def test_parent_cancellation_cascades_to_handoffs_and_child_tasks():
    sql = re.sub(r"\s+", " ", _collaboration_lifecycle_migration())
    assert "cancel_engine_collaboration_children_on_parent_cancel" in sql
    assert "old.cancel_requested_at is not null or new.cancel_requested_at is null" in sql
    assert "h.status in ('pending_approval','approved','running')" in sql
    assert "child_task_id" in sql
    assert "child.status in ('ready','running','cancel_requested')" in sql
    assert "cancel_requested_at = coalesce(child.cancel_requested_at,now())" in sql
    assert "'handoff.cancelled','cancelled'" in sql
    assert "from public.engine_collaboration_events" in sql


def test_child_terminal_state_is_persisted_as_metadata_only_handoff_event():
    sql = re.sub(r"\s+", " ", _collaboration_lifecycle_migration())
    assert "record_engine_collaboration_child_terminal" in sql
    assert "new.status not in ('completed','failed','cancelled')" in sql
    assert "when 'completed' then 'handoff.completed'" in sql
    assert "when 'failed' then 'handoff.failed'" in sql
    assert "else 'handoff.cancelled'" in sql
    assert "where h.child_task_id = new.id" in sql
    assert "jsonb_build_object('child_task_id',new.id,'child_status',new.status)" in sql
    assert "from public.task_steps" not in sql
    assert "revoke all on function public.record_engine_collaboration_child_terminal() from public,anon,authenticated" in sql


def _parent_child_continuation_migration() -> str:
    root = Path(__file__).resolve().parents[3]
    return (root / "supabase" / "migrations" / "20261122070000_durable_parent_child_continuation.sql").read_text(encoding="utf-8")


def test_parent_wait_state_and_approval_support_multiple_sibling_handoffs():
    sql = re.sub(r"\s+", " ", _parent_child_continuation_migration())
    assert "'waiting_children'" in sql
    assert "v_task.status not in ('running','completed','waiting_children')" in sql
    assert "v_parent.status not in ('running','completed','waiting_children')" in sql
    assert "after insert on public.engine_collaboration_handoffs" in sql
    assert "after insert on public.hermes_delegation_outbox" in sql
    assert "set status = 'waiting_children'" in sql


def test_parent_resumes_only_after_all_sibling_handoffs_and_outbox_rows_are_terminal():
    sql = re.sub(r"\s+", " ", _parent_child_continuation_migration())
    assert "maybe_queue_engine_parent_continuation" in sql
    assert "o.status in ('pending','processing')" in sql
    assert "h.status in ('pending_approval','approved','running')" in sql
    assert "new.status in ('submitted','failed')" in sql
    assert "new.status in ('completed','failed','cancelled','rejected')" in sql
    assert "on conflict (task_id,step_key) do nothing" in sql
    assert "v_step_key := 'resume_' || replace(p_parent_run_id::text,'-','')" in sql
    assert "set status = 'ready'" in sql
    assert "t.status = 'waiting_children'" in sql
    assert "t.cancel_requested_at is null" in sql


def test_parent_continuation_includes_bounded_owner_scoped_child_results_as_untrusted_context():
    sql = re.sub(r"\s+", " ", _parent_child_continuation_migration())
    assert "s.task_id = h.child_task_id" in sql
    assert "s.user_id = p_user_id" in sql
    assert "left(s.output::text,2200)" in sql
    assert "left(v_outcomes::text,8000)" in sql
    assert "<UNTRUSTED_CHILD_RESULTS>" in sql
    assert "SULY_PARENT_CONTINUATION_V1" in sql
    assert "runtime_budget_seconds" in sql
    assert "continuation_of_run_id" in sql


def test_parent_cancellation_and_duplicate_child_terminal_triggers_remain_single_writer():
    sql = re.sub(r"\s+", " ", _parent_child_continuation_migration())
    assert "drop trigger if exists tasks_sync_engine_collaboration_child on public.tasks" in sql
    assert "drop trigger if exists tasks_record_engine_collaboration_child_terminal on public.tasks" in sql
    assert "create trigger tasks_record_engine_collaboration_child_terminal" in sql
    assert "where h.child_task_id = new.id" in sql
    assert "h.status in ('approved','running')" in sql
    assert "from public.engine_collaboration_events" in sql
