-- SULY worker lease and checkpoint protocol.
alter table public.task_steps
  add column available_at timestamptz not null default now();

create index task_steps_available_idx
  on public.task_steps (available_at, task_id, step_order)
  where status = 'pending';

create or replace function public.claim_task_step(
  p_worker_id text,
  p_lease_seconds integer default 90
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_step public.task_steps%rowtype;
begin
  if p_worker_id is null or char_length(btrim(p_worker_id)) not between 1 and 120
     or p_lease_seconds not between 15 and 900 then
    raise exception 'invalid_worker_claim_parameters';
  end if;

  -- Expired leases are retried only while attempts remain.
  update public.task_steps
     set status = case when attempt_count < max_attempts then 'pending' else 'failed' end,
         lease_owner = null, lease_token = null, lease_expires_at = null,
         available_at = now(),
         error_code = case when attempt_count >= max_attempts then 'lease_expired' else error_code end,
         error_message = case when attempt_count >= max_attempts then 'Worker lease expired after maximum attempts.' else error_message end
   where status = 'running' and lease_expires_at <= now();

  update public.tasks t
     set status = 'failed', error_code = 'step_attempts_exhausted',
         error_message = 'A task step exhausted its retry attempts.', completed_at = now()
   where t.status in ('ready','running')
     and exists (select 1 from public.task_steps s where s.task_id=t.id and s.status='failed');

  -- Cancellation is cooperative: revoke leases and stop unclaimed work.
  update public.task_steps s
     set status = 'cancelled', lease_owner = null, lease_token = null,
         lease_expires_at = null, completed_at = coalesce(completed_at, now())
    from public.tasks t
   where s.task_id=t.id and t.status='cancel_requested'
     and s.status in ('pending','ready','running');

  update public.tasks t
     set status='cancelled', completed_at=coalesce(completed_at,now())
   where t.status='cancel_requested'
     and not exists (select 1 from public.task_steps s where s.task_id=t.id and s.status='running');

  -- Promote fully completed plans to a terminal task state.
  update public.tasks t
     set status='completed', completed_at=coalesce(completed_at,now())
   where t.status in ('ready','running')
     and exists (select 1 from public.task_steps s where s.task_id=t.id)
     and not exists (select 1 from public.task_steps s where s.task_id=t.id and s.status <> 'completed');

  select s.* into v_step
    from public.task_steps s
    join public.tasks t on t.id=s.task_id
   where s.status='pending'
     and s.available_at <= now()
     and t.status in ('ready','running')
     and t.cancel_requested_at is null
     and not exists (
       select 1
         from jsonb_array_elements_text(s.depends_on) d(step_key)
         where not exists (
           select 1 from public.task_steps dep
            where dep.task_id=s.task_id
              and dep.step_key=d.step_key
              and dep.status='completed'
         )
     )
   order by t.created_at, s.step_order
   for update of s skip locked
   limit 1;

  if not found then
    return null;
  end if;

  update public.task_steps
     set status='running', attempt_count=attempt_count+1,
         lease_owner=btrim(p_worker_id), lease_token=pg_catalog.gen_random_uuid(),
         lease_expires_at=now() + pg_catalog.make_interval(secs => p_lease_seconds),
         started_at=coalesce(started_at,now()), error_code=null, error_message=null
   where id=v_step.id
   returning * into v_step;

  update public.tasks
     set status='running', started_at=coalesce(started_at,now())
   where id=v_step.task_id and status='ready';

  return pg_catalog.jsonb_build_object(
    'step_id',v_step.id,'task_id',v_step.task_id,'user_id',v_step.user_id,
    'step_key',v_step.step_key,'title',v_step.title,'description',v_step.description,
    'input',v_step.input,'attempt_count',v_step.attempt_count,
    'max_attempts',v_step.max_attempts,'lease_token',v_step.lease_token,
    'lease_expires_at',v_step.lease_expires_at
  );
end;
$$;

create or replace function public.renew_task_step_lease(
  p_step_id uuid, p_lease_token uuid, p_lease_seconds integer default 90
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare v_updated integer;
begin
  if p_lease_seconds not between 15 and 900 then raise exception 'invalid_lease_duration'; end if;
  update public.task_steps s
     set lease_expires_at=now() + pg_catalog.make_interval(secs => p_lease_seconds)
    from public.tasks t
   where s.id=p_step_id and s.task_id=t.id
     and s.status='running' and s.lease_token=p_lease_token
     and s.lease_expires_at > now()
     and t.status='running' and t.cancel_requested_at is null;
  get diagnostics v_updated = row_count;
  return v_updated = 1;
end;
$$;

create or replace function public.complete_task_step(
  p_step_id uuid, p_lease_token uuid, p_output jsonb
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare v_task_id uuid; v_cancel boolean;
begin
  if p_output is null or pg_catalog.jsonb_typeof(p_output) <> 'object' then
    raise exception 'step_output_must_be_object';
  end if;

  update public.task_steps s
     set status=case when t.cancel_requested_at is null then 'completed' else 'cancelled' end,
         output=p_output, completed_at=now(),
         lease_owner=null, lease_token=null, lease_expires_at=null
    from public.tasks t
   where s.id=p_step_id and s.task_id=t.id
     and s.status='running' and s.lease_token=p_lease_token
     and s.lease_expires_at > now()
   returning s.task_id into v_task_id;
  select (cancel_requested_at is not null) into v_cancel from public.tasks where id=v_task_id;
  if not found then return false; end if;

  if v_cancel then
    update public.task_steps
       set status='cancelled', completed_at=coalesce(completed_at,now())
     where task_id=v_task_id and status in ('pending','ready');
    update public.tasks
       set status='cancelled', completed_at=coalesce(completed_at,now())
     where id=v_task_id and status='cancel_requested'
       and not exists (select 1 from public.task_steps s where s.task_id=v_task_id and s.status='running');
  else
    update public.tasks
       set status='completed', completed_at=coalesce(completed_at,now())
     where id=v_task_id and status in ('ready','running')
       and not exists (select 1 from public.task_steps s where s.task_id=v_task_id and s.status <> 'completed');
  end if;
  return true;
end;
$$;

create or replace function public.fail_task_step(
  p_step_id uuid, p_lease_token uuid, p_error_code text, p_error_message text
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare v_step public.task_steps%rowtype; v_task_cancelled boolean;
begin
  update public.task_steps s
     set status=case
           when t.cancel_requested_at is not null then 'cancelled'
           when s.attempt_count < s.max_attempts then 'pending'
           else 'failed' end,
         error_code=left(coalesce(nullif(btrim(p_error_code),''),'worker_error'),80),
         error_message=left(coalesce(p_error_message,'Worker step failed.'),2000),
         available_at=case when t.cancel_requested_at is null and s.attempt_count < s.max_attempts
           then now() + pg_catalog.make_interval(secs => least(300, 5 * pg_catalog.power(2,greatest(s.attempt_count - 1,0))::integer))
           else now() end,
         completed_at=case when t.cancel_requested_at is not null or s.attempt_count >= s.max_attempts then now() else null end,
         lease_owner=null, lease_token=null, lease_expires_at=null
    from public.tasks t
   where s.id=p_step_id and s.task_id=t.id
     and s.status='running' and s.lease_token=p_lease_token
     and s.lease_expires_at > now()
   returning s.*, (t.cancel_requested_at is not null)
        into v_step, v_task_cancelled;
  if not found then return pg_catalog.jsonb_build_object('accepted',false); end if;

  if v_task_cancelled then
    update public.task_steps set status='cancelled', completed_at=coalesce(completed_at,now())
     where task_id=v_step.task_id and status in ('pending','ready');
    update public.tasks set status='cancelled', completed_at=coalesce(completed_at,now())
     where id=v_step.task_id and status='cancel_requested'
       and not exists (select 1 from public.task_steps s where s.task_id=v_step.task_id and s.status='running');
  elsif v_step.status='failed' then
    update public.tasks set status='failed', error_code='step_attempts_exhausted',
      error_message='A task step exhausted its retry attempts.', completed_at=now()
     where id=v_step.task_id and status in ('ready','running');
  end if;

  return pg_catalog.jsonb_build_object(
    'accepted',true,'step_status',v_step.status,
    'attempt_count',v_step.attempt_count,'max_attempts',v_step.max_attempts,
    'available_at',v_step.available_at
  );
end;
$$;

revoke all on function public.claim_task_step(text,integer) from public, anon, authenticated;
revoke all on function public.renew_task_step_lease(uuid,uuid,integer) from public, anon, authenticated;
revoke all on function public.complete_task_step(uuid,uuid,jsonb) from public, anon, authenticated;
revoke all on function public.fail_task_step(uuid,uuid,text,text) from public, anon, authenticated;
grant execute on function public.claim_task_step(text,integer) to service_role;
grant execute on function public.renew_task_step_lease(uuid,uuid,integer) to service_role;
grant execute on function public.complete_task_step(uuid,uuid,jsonb) to service_role;
grant execute on function public.fail_task_step(uuid,uuid,text,text) to service_role;

comment on function public.claim_task_step(text,integer) is 'Atomically claims one dependency-ready task step using SKIP LOCKED and an expiring opaque lease. Service role only.';
comment on function public.renew_task_step_lease(uuid,uuid,integer) is 'Renews a live step lease only when the opaque lease token matches. Service role only.';
comment on function public.complete_task_step(uuid,uuid,jsonb) is 'Commits a step output checkpoint only for the current unexpired lease token. Service role only.';
comment on function public.fail_task_step(uuid,uuid,text,text) is 'Records a failure and schedules bounded exponential retry, or terminally fails the task. Service role only.';
