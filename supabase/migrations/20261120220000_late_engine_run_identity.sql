-- Preserve late upstream identity when the worker loses its lease during run admission.
-- لا نغلق محاولة Hermes قبل فرصة حفظ معرف التشغيل الخارجي المتأخر.

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

  -- heartbeat بنفس token لا ينهي ملكية العامل.
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
           -- Hermes قد يرجع run_id بعد انتهاء lease؛ احتفظ بالسجل لحين وصوله ومحاولة إيقافه.
           when r.engine_id = 'hermes-agent' or r.upstream_run_id is not null
             then 'stop_pending'
           when coalesce(v_cancel_requested, false) or new.status = 'cancelled'
             then 'cancelled'
           else 'failed'
         end,
         error_code = case
           when r.engine_id = 'hermes-agent' or r.upstream_run_id is not null then null
           when coalesce(v_cancel_requested, false) or new.status = 'cancelled' then null
           when old.lease_expires_at is not null and old.lease_expires_at <= now()
             then 'engine_lease_expired'
           else 'engine_step_ended'
         end,
         completed_at = case
           when r.engine_id = 'hermes-agent' or r.upstream_run_id is not null then null
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

-- يسمح بحفظ معرف Hermes المتأخر في stop_pending، لكن لا يمنح العامل القديم حق الإكمال.
create or replace function public.attach_engine_upstream_run(
  p_run_id uuid,
  p_step_id uuid,
  p_lease_token uuid,
  p_upstream_run_id text
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rows integer;
begin
  if p_upstream_run_id is null
     or p_upstream_run_id !~ '^[A-Za-z0-9_-]{1,128}$' then
    raise exception 'invalid_upstream_run_id';
  end if;

  update public.engine_runs r
     set upstream_run_id = p_upstream_run_id,
         updated_at = now()
    from public.task_steps s
   where r.id = p_run_id
     and r.step_id = p_step_id
     and s.id = r.step_id
     and s.task_id = r.task_id
     and s.user_id = r.user_id
     and r.engine_id = 'hermes-agent'
     and r.status in ('running','stop_pending')
     and (r.upstream_run_id is null or r.upstream_run_id = p_upstream_run_id)
     and (
       r.status = 'stop_pending'
       or (
         s.status = 'running'
         and s.attempt_count = r.attempt_count
         and s.lease_token = p_lease_token
         and s.lease_expires_at > now()
         and not exists (
           select 1 from public.tasks t
            where t.id = s.task_id and t.cancel_requested_at is not null
         )
       )
     );

  get diagnostics v_rows = row_count;
  if v_rows <> 1 then
    return false;
  end if;

  -- true تعني أن التنفيذ ما زال يملك lease؛ false تعني أن المرجع حُفظ
  -- لكن يجب إيقاف Hermes فورًا لأن المحاولة أصبحت orphan/stop_pending.
  return exists (
    select 1
      from public.engine_runs r
      join public.task_steps s on s.id = r.step_id
      join public.tasks t on t.id = s.task_id
     where r.id = p_run_id
       and r.status = 'running'
       and s.status = 'running'
       and s.attempt_count = r.attempt_count
       and s.lease_token = p_lease_token
       and s.lease_expires_at > now()
       and t.cancel_requested_at is null
  );
end;
$$;

revoke all on function public.attach_engine_upstream_run(uuid,uuid,uuid,text)
  from public, anon, authenticated;
grant execute on function public.attach_engine_upstream_run(uuid,uuid,uuid,text)
  to service_role;

comment on function public.attach_engine_upstream_run(uuid,uuid,uuid,text) is
  'Persists a Hermes run ID for the matching engine attempt. A late ID may be attached to stop_pending for cleanup, but never restores execution ownership.';
