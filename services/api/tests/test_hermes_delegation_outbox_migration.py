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


def test_parent_resume_step_is_claimed_only_after_its_exact_run_barrier_is_clear():
    sql = re.sub(r"\s+", " ", _parent_child_continuation_migration())
    assert "create or replace function public.claim_task_step(" in sql
    assert "t.status = 'waiting_children'" in sql
    assert "left(s.step_key,7) = 'resume_'" in sql
    assert "r.id::text = s.input->>'continuation_of_run_id'" in sql
    assert "r.status = 'succeeded'" in sql
    assert "o.parent_run_id::text = s.input->>'continuation_of_run_id'" in sql
    assert "h.parent_run_id::text = s.input->>'continuation_of_run_id'" in sql
    assert "set status='running'" in sql
    assert "and cancel_requested_at is null" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "set status = 'ready'" not in sql


def _opencode_post_apply_migration() -> str:
    root = Path(__file__).resolve().parents[3]
    return (root / "supabase" / "migrations" / "20261122080000_opencode_post_apply_review_and_handoff_gate.sql").read_text(encoding="utf-8")


def test_opencode_apply_queues_one_durable_post_apply_review_without_recursive_review_loops():
    sql = re.sub(r"\s+", " ", _opencode_post_apply_migration())
    assert "enqueue_opencode_post_apply_review" in sql
    assert "new.status is not distinct from old.status" in sql
    assert "new.status <> 'applied'" in sql
    assert "v_source_step.input ? 'review_of_change_set_id'" in sql
    assert "review_after_apply_" in sql
    assert "'review_of_change_set_id',new.id" in sql
    assert "Perform a post-apply review" not in sql
    assert "لا تعدّل الملفات ولا تطبق أي تغيير بنفسك" in sql
    assert "on conflict (task_id,step_key) do nothing" in sql
    assert "set status = 'ready'" in sql


def test_opencode_child_handoff_waits_for_owner_change_set_decision_and_rereview():
    sql = re.sub(r"\s+", " ", _opencode_post_apply_migration())
    assert "cs.status in ('review_ready','applying')" in sql
    assert "sync_opencode_change_set_handoff_terminal" in sql
    assert "new.status not in ('applied','rejected','stale')" in sql
    assert "if new.status = 'applied' and not v_handoff.is_re_review then continue" in sql
    assert "'re_review_applied'" in sql
    assert "'re_review_rejected'" in sql
    assert "review_decision = v_decision" in sql
    assert "after update of status on public.opencode_change_sets" in sql


def test_parent_continuation_preserves_opencode_review_outcome_and_claim_barrier():
    sql = re.sub(r"\s+", " ", _parent_child_continuation_migration())
    assert "add column if not exists review_decision text" in sql
    assert "'review_decision',h.review_decision" in sql
    assert "waiting_children" in sql
    assert "left(s.step_key,7) = 'resume_'" in sql


def test_post_apply_review_waits_for_remaining_dag_steps_and_is_not_recursive():
    sql = re.sub(r"\s+", " ", _opencode_post_apply_migration())
    assert "t.status in ('completed','ready','running')" in sql
    assert "v_dependencies" in sql
    assert "s.status in ('pending','ready','running')" in sql
    assert "v_source_step.input ? 'review_of_change_set_id'" in sql
    assert "if v_parent.status = 'completed' then" in sql
    assert "'review_of_change_set_id',new.id" in sql


def test_resume_claim_rechecks_late_handoff_race_and_does_not_consume_attempt():
    sql = re.sub(r"\s+", " ", _parent_child_continuation_migration())
    assert "collaboration_parent_run_already_resumed" in sql
    assert "attempt_count=greatest(attempt_count-1,0)" in sql
    assert "status='pending'" in sql
    assert "left(v_step.step_key,7) <> 'resume_'" in sql
    assert "o.parent_run_id::text = v_step.input->>'continuation_of_run_id'" in sql
    assert "h.parent_run_id::text = v_step.input->>'continuation_of_run_id'" in sql


def test_opencode_apply_is_blocked_after_child_or_parent_cancellation():
    sql = re.sub(r"\s+", " ", _opencode_post_apply_migration())
    assert "guard_opencode_change_set_apply_after_cancellation" in sql
    assert "new.status not in ('applying','applied')" in sql
    assert "v_task_status in ('cancel_requested','cancelled')" in sql
    assert "h.status in ('cancelled','failed')" in sql
    assert "raise exception 'opencode_task_cancelled'" in sql
    assert "before update of status on public.opencode_change_sets" in sql


def test_continuation_prompts_are_utf8_byte_bounded_for_engine_input_contracts():
    parent = re.sub(r"\s+", " ", _parent_child_continuation_migration())
    opencode = re.sub(r"\s+", " ", _opencode_post_apply_migration())
    assert "octet_length(v_prompt) > 30000" in parent
    assert "octet_length(v_prompt) > 44000" in opencode
    assert "collaboration_parent_run_already_resumed" in parent
