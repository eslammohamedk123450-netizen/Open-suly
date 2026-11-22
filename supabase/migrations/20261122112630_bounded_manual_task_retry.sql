-- Bounded user-requested retries for terminally failed tasks.
alter table public.tasks
  add column manual_retry_count integer not null default 0
  check (manual_retry_count between 0 and 2);

create or replace function public.retry_failed_task(
  p_task_id uuid,
  p_user_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_task public.tasks%rowtype;
  v_reset integer;
begin
  select * into v_task
    from public.tasks
   where id = p_task_id and user_id = p_user_id
   for update;

  if not found then
    raise exception 'task_not_found';
  end if;
  if v_task.status <> 'failed' then
    raise exception 'task_not_failed';
  end if;
  if v_task.manual_retry_count >= 2 then
    raise exception 'manual_retry_limit_reached';
  end if;

  update public.task_steps
     set status = 'pending',
         attempt_count = 0,
         available_at = now(),
         error_code = null,
         error_message = null,
         completed_at = null,
         lease_owner = null,
         lease_token = null,
         lease_expires_at = null
   where task_id = p_task_id
     and user_id = p_user_id
     and status = 'failed';

  get diagnostics v_reset = row_count;
  if v_reset = 0 then
    raise exception 'no_failed_steps_to_retry';
  end if;

  update public.tasks
     set status = 'ready',
         manual_retry_count = manual_retry_count + 1,
         error_code = null,
         error_message = null,
         completed_at = null,
         cancel_requested_at = null
   where id = p_task_id and user_id = p_user_id;

  return pg_catalog.jsonb_build_object(
    'task_id', p_task_id,
    'status', 'ready',
    'reset_steps', v_reset,
    'manual_retry_count', v_task.manual_retry_count + 1,
    'manual_retry_limit', 2
  );
end;
$$;

revoke all on function public.retry_failed_task(uuid,uuid) from public, anon, authenticated;
grant execute on function public.retry_failed_task(uuid,uuid) to service_role;
comment on function public.retry_failed_task(uuid,uuid) is
  'Resets only failed steps for an owned terminal task, with at most two user-requested retries.';
