-- Preserve external runs for cooperative stop after lease loss/cancellation.
-- هذه الهجرة تفصل بين إنهاء ملكية المهمة وإثبات توقف العملية الخارجية.

alter table public.engine_runs
  drop constraint if exists engine_runs_status_check;
alter table public.engine_runs
  add constraint engine_runs_status_check
  check (status in ('running','stop_pending','succeeded','failed','cancelled'));

alter table public.engine_runs
  drop constraint if exists engine_runs_check;
alter table public.engine_runs
  add constraint engine_runs_completion_check
  check ((status in ('running','stop_pending')) = (completed_at is null));

alter table public.engine_runs
  add column if not exists reconcile_token uuid,
  add column if not exists reconcile_lease_expires_at timestamptz,
  add column if not exists reconcile_attempt_count integer not null default 0
    check (reconcile_attempt_count between 0 and 1000);

create index if not exists engine_runs_stop_pending_idx
  on public.engine_runs(reconcile_lease_expires_at, started_at)
  where status = 'stop_pending';

-- عند انتهاء lease، لا نغلق سجل تشغيل خارجي قبل محاولة إيقافه.
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

  -- تجديد lease بنفس الرمز لا ينهي المحاولة.
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
           when r.upstream_run_id is not null then 'stop_pending'
           when coalesce(v_cancel_requested, false) or new.status = 'cancelled' then 'cancelled'
           else 'failed'
         end,
         error_code = case
           when r.upstream_run_id is not null then null
           when coalesce(v_cancel_requested, false) or new.status = 'cancelled' then null
           when old.lease_expires_at is not null and old.lease_expires_at <= now()
             then 'engine_lease_expired'
           else 'engine_step_ended'
         end,
         completed_at = case
           when r.upstream_run_id is not null then null
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

revoke all on function public.reconcile_engine_run_on_step_transition()
  from public, anon, authenticated;
grant execute on function public.reconcile_engine_run_on_step_transition()
  to service_role;

-- مصالحة دورية: السجل الذي يحمل معرفًا خارجيًا ينتقل إلى stop_pending.
-- أما السجل الذي لم يبدأ خارجيًا فيغلق مباشرة برمز آمن.
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
           when c.upstream_run_id is not null then 'stop_pending'
           when c.was_cancelled then 'cancelled'
           else 'failed'
         end,
         error_code = case
           when c.upstream_run_id is not null or c.was_cancelled then null
           when c.lease_expired then 'engine_lease_expired'
           else 'engine_step_ended'
         end,
         completed_at = case
           when c.upstream_run_id is not null then null
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

-- حجز ذري لسجلات الإيقاف؛ يسمح بإعادة المحاولة بعد انتهاء reconciliation lease.
create or replace function public.claim_engine_runs_for_stop(
  p_batch_size integer default 10,
  p_lease_seconds integer default 60
)
returns table (
  run_id uuid,
  engine_id text,
  upstream_run_id text,
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
       and r.upstream_run_id is not null
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
  returning r.id, r.engine_id, r.upstream_run_id, r.reconcile_token, r.reconcile_attempt_count;
end;
$$;

-- لا نغلق سجل المحرك إلا بعد تأكيد أن التشغيل الخارجي أصبح في حالة نهائية.
-- عند فشل الإيقاف نحرر الحجز مع backoff حتى لا نغرق الخدمة بطلبات متكررة.
create or replace function public.finish_engine_run_reconciliation(
  p_run_id uuid,
  p_reconcile_token uuid,
  p_stop_confirmed boolean
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rows integer;
begin
  if p_stop_confirmed is null then
    raise exception 'invalid_engine_stop_confirmation';
  end if;

  update public.engine_runs r
     set status = case
           when p_stop_confirmed and (
             t.cancel_requested_at is not null or s.status = 'cancelled'
           ) then 'cancelled'
           when p_stop_confirmed then 'failed'
           else 'stop_pending'
         end,
         error_code = case
           when not p_stop_confirmed then null
           when t.cancel_requested_at is not null or s.status = 'cancelled' then null
           when s.lease_expires_at is not null and s.lease_expires_at <= now()
             then 'engine_lease_expired'
           else 'engine_step_ended'
         end,
         completed_at = case
           when p_stop_confirmed then coalesce(r.completed_at, now())
           else null
         end,
         reconcile_token = null,
         reconcile_lease_expires_at = case
           when p_stop_confirmed then null
           else now() + make_interval(
             secs => least(3600, 5 * (2 ^ least(r.reconcile_attempt_count, 9))::integer)
           )
         end,
         updated_at = now()
    from public.task_steps s
    join public.tasks t on t.id = s.task_id and t.user_id = s.user_id
   where r.id = p_run_id
     and r.step_id = s.id
     and r.task_id = s.task_id
     and r.user_id = s.user_id
     and r.status = 'stop_pending'
     and r.reconcile_token = p_reconcile_token;

  get diagnostics v_rows = row_count;
  return v_rows = 1;
end;
$$;

revoke all on function public.reconcile_orphan_engine_runs(integer)
  from public, anon, authenticated;
revoke all on function public.claim_engine_runs_for_stop(integer,integer)
  from public, anon, authenticated;
revoke all on function public.finish_engine_run_reconciliation(uuid,uuid,boolean)
  from public, anon, authenticated;
grant execute on function public.reconcile_orphan_engine_runs(integer)
  to service_role;
grant execute on function public.claim_engine_runs_for_stop(integer,integer)
  to service_role;
grant execute on function public.finish_engine_run_reconciliation(uuid,uuid,boolean)
  to service_role;

comment on column public.engine_runs.reconcile_token is
  'Opaque service-only lease token used by the external engine stop reconciler.';
comment on column public.engine_runs.reconcile_lease_expires_at is
  'Lease expiry for a reconciler claim; failed stop attempts are retried with bounded backoff.';
