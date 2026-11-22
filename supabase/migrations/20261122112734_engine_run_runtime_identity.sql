-- Persist the opaque runtime identity for lease-scoped control/recovery.
-- Never persist the short-lived runtime access token or provider credentials.

alter table public.engine_runs
  add column if not exists runtime_id uuid;

create unique index if not exists engine_runs_runtime_identity_idx
  on public.engine_runs(runtime_id)
  where runtime_id is not null;

create or replace function public.attach_engine_runtime_identity(
  p_run_id uuid,
  p_step_id uuid,
  p_lease_token uuid,
  p_runtime_id uuid
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rows integer;
begin
  if p_runtime_id is null then
    raise exception 'invalid_engine_runtime_id';
  end if;

  update public.engine_runs r
     set runtime_id = p_runtime_id,
         updated_at = now()
    from public.task_steps s
   where r.id = p_run_id
     and r.step_id = p_step_id
     and s.id = r.step_id
     and s.task_id = r.task_id
     and s.user_id = r.user_id
     and s.status = 'running'
     and s.lease_token = p_lease_token
     and s.lease_expires_at > now()
     and r.status = 'running'
     and (r.runtime_id is null or r.runtime_id = p_runtime_id)
     and not exists (
       select 1
         from public.tasks t
        where t.id = s.task_id
          and t.cancel_requested_at is not null
     );

  get diagnostics v_rows = row_count;
  return v_rows = 1;
end;
$$;

revoke all on function public.attach_engine_runtime_identity(uuid,uuid,uuid,uuid)
  from public, anon, authenticated;
grant execute on function public.attach_engine_runtime_identity(uuid,uuid,uuid,uuid)
  to service_role;

comment on column public.engine_runs.runtime_id is
  'Opaque isolated runtime identity only; never a runtime token or credential.';
