-- Extend cooperative stop recovery to task-scoped Hermes runtimes.
-- A runtime may exist before Hermes returns an upstream run ID, so the
-- runtime identity itself is sufficient to require cleanup after lease loss.

create or replace function public.reconcile_engine_run_on_step_transition()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_cancel_requested boolean := false;
begin
  if old.status <> 'running' then
    return new;
  end if;

  if new.status = 'running'
     and new.lease_token is not distinct from old.lease_token then
    return new;
  end if;

  select (t.cancel_requested_at is not null)
    into v_cancel_requested
    from public.tasks t
   where t.id = old.task_id
     and t.user_id = old.user_id;

  update public.engine_runs r
     set status = case
           when r.upstream_run_id is not null or r.runtime_id is not null then 'stop_pending'
           when coalesce(v_cancel_requested, false) or new.status = 'cancelled' then 'cancelled'
           else 'failed'
         end,
         error_code = case
           when r.upstream_run_id is not null or r.runtime_id is not null then null
           when coalesce(v_cancel_requested, false) or new.status = 'cancelled' then null
           when old.lease_expires_at is not null and old.lease_expires_at <= now()
             then 'engine_lease_expired'
           else 'engine_step_ended'
         end,
         completed_at = case
           when r.upstream_run_id is not null or r.runtime_id is not null then null
           else coalesce(r.completed_at, now())
         end,
         updated_at = now()
   where r.step_id = old.id
     and r.task_id = old.task_id
     and r.user_id = old.user_id
     and r.attempt_count = old.attempt_count
     and r.status = 'running';

  return new;
end;
$$;

create or replace function public.reconcile_orphan_engine_runs(
  p_batch_size integer default 100
)
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rows integer;
begin
  if p_batch_size is null or p_batch_size not between 1 and 500 then
    raise exception 'invalid_reconciliation_batch_size';
  end if;

  with candidates as (
    select r.id,
           r.upstream_run_id,
           r.runtime_id,
           (t.cancel_requested_at is not null or s.status = 'cancelled') as was_cancelled,
           (s.lease_expires_at is not null and s.lease_expires_at <= now()) as lease_expired
      from public.engine_runs r
      join public.task_steps s
        on s.id = r.step_id and s.task_id = r.task_id and s.user_id = r.user_id
      join public.tasks t
        on t.id = s.task_id and t.user_id = s.user_id
     where r.status = 'running'
       and (
         s.status <> 'running'
         or s.lease_expires_at is null
         or s.lease_expires_at <= now()
         or t.cancel_requested_at is not null
       )
     order by r.started_at, r.id
     for update of r skip locked
     limit p_batch_size
  )
  update public.engine_runs r
     set status = case
           when c.upstream_run_id is not null or c.runtime_id is not null then 'stop_pending'
           when c.was_cancelled then 'cancelled'
           else 'failed'
         end,
         error_code = case
           when c.upstream_run_id is not null or c.runtime_id is not null or c.was_cancelled then null
           when c.lease_expired then 'engine_lease_expired'
           else 'engine_step_ended'
         end,
         completed_at = case
           when c.upstream_run_id is not null or c.runtime_id is not null then null
           else coalesce(r.completed_at, now())
         end,
         updated_at = now()
    from candidates c
   where r.id = c.id
     and r.status = 'running';

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

create or replace function public.claim_engine_runs_for_stop(
  p_batch_size integer default 10,
  p_lease_seconds integer default 60
)
returns table (
  run_id uuid,
  task_id uuid,
  engine_id text,
  upstream_run_id text,
  runtime_id uuid,
  reconcile_token uuid,
  reconcile_attempt_count integer
)
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if p_batch_size is null or p_batch_size not between 1 and 100
     or p_lease_seconds is null or p_lease_seconds not between 15 and 900 then
    raise exception 'invalid_engine_stop_claim_bounds';
  end if;

  return query
  with candidates as (
    select r.id
      from public.engine_runs r
     where r.status = 'stop_pending'
       and (r.upstream_run_id is not null or r.runtime_id is not null)
       and (r.reconcile_lease_expires_at is null or r.reconcile_lease_expires_at <= now())
     order by r.started_at, r.id
     for update skip locked
     limit p_batch_size
  )
  update public.engine_runs r
     set reconcile_token = gen_random_uuid(),
         reconcile_lease_expires_at = now() + make_interval(secs => p_lease_seconds),
         reconcile_attempt_count = least(r.reconcile_attempt_count + 1, 1000),
         updated_at = now()
    from candidates c
   where r.id = c.id
  returning r.id, r.task_id, r.engine_id, r.upstream_run_id, r.runtime_id,
            r.reconcile_token, r.reconcile_attempt_count;
end;
$$;

revoke all on function public.reconcile_engine_run_on_step_transition()
  from public, anon, authenticated;
revoke all on function public.reconcile_orphan_engine_runs(integer)
  from public, anon, authenticated;
revoke all on function public.claim_engine_runs_for_stop(integer,integer)
  from public, anon, authenticated;
grant execute on function public.reconcile_orphan_engine_runs(integer)
  to service_role;
grant execute on function public.claim_engine_runs_for_stop(integer,integer)
  to service_role;

comment on function public.claim_engine_runs_for_stop(integer,integer) is
  'Claims stale external engine runs with either an upstream run ID or an isolated runtime ID for cooperative stop and runtime cleanup.';
