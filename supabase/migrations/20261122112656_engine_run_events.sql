-- Durable, metadata-only Hermes progress events owned by the SULY task lease.
-- Event payload text, tool arguments, previews, and outputs are deliberately excluded.

create table public.engine_run_events (
  id bigint generated always as identity primary key,
  engine_run_id uuid not null references public.engine_runs(id) on delete cascade,
  task_id uuid not null,
  user_id uuid not null,
  event_name text not null check (event_name in (
    'tool.started', 'tool.completed', 'subagent.start', 'subagent.complete',
    'run.queued', 'run.completed', 'run.failed', 'run.cancelled',
    'run.interrupted', 'run.stopping', 'run.steered',
    'approval.request', 'approval.responded'
  )),
  event_seq bigint check (event_seq is null or event_seq >= 0),
  event_timestamp double precision check (
    event_timestamp is null or event_timestamp between 0 and 4102444800
  ),
  received_at timestamptz not null default now(),
  constraint engine_run_events_owner_fkey
    foreign key (task_id, user_id) references public.tasks(id, user_id) on delete cascade
);

create index engine_run_events_task_received_idx
  on public.engine_run_events(task_id, user_id, received_at, id);
create unique index engine_run_events_run_seq_uidx
  on public.engine_run_events(engine_run_id, event_seq)
  where event_seq is not null;

alter table public.engine_run_events enable row level security;
create policy engine_run_events_select_own on public.engine_run_events
  for select to authenticated using ((select auth.uid()) = user_id);
grant select on public.engine_run_events to authenticated;
revoke insert, update, delete on public.engine_run_events from anon, authenticated;
grant all on public.engine_run_events to service_role;

create or replace function public.append_engine_run_event(
  p_run_id uuid,
  p_step_id uuid,
  p_lease_token uuid,
  p_event_name text,
  p_event_seq bigint default null,
  p_event_timestamp double precision default null
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rows integer;
  v_user_id uuid;
  v_task_id uuid;
begin
  if p_event_name is null or p_event_name not in (
    'tool.started', 'tool.completed', 'subagent.start', 'subagent.complete',
    'run.queued', 'run.completed', 'run.failed', 'run.cancelled',
    'run.interrupted', 'run.stopping', 'run.steered',
    'approval.request', 'approval.responded'
  ) then
    raise exception 'invalid_engine_run_event_name';
  end if;
  if p_event_seq is not null and p_event_seq < 0 then
    raise exception 'invalid_engine_run_event_sequence';
  end if;
  if p_event_timestamp is not null
     and (p_event_timestamp < 0 or p_event_timestamp > 4102444800) then
    raise exception 'invalid_engine_run_event_timestamp';
  end if;

  select r.user_id, r.task_id into v_user_id, v_task_id
    from public.engine_runs r
    join public.task_steps s
      on s.id = r.step_id and s.task_id = r.task_id and s.user_id = r.user_id
   where r.id = p_run_id
     and r.step_id = p_step_id
     and r.status = 'running'
     and s.status = 'running'
     and s.lease_token = p_lease_token
     and s.lease_expires_at > now()
   for update of r;

  if not found then
    return false;
  end if;

  insert into public.engine_run_events (
    engine_run_id, task_id, user_id, event_name, event_seq, event_timestamp
  ) values (
    p_run_id, v_task_id, v_user_id, p_event_name, p_event_seq, p_event_timestamp
  )
  on conflict (engine_run_id, event_seq) where event_seq is not null do nothing;

  get diagnostics v_rows = row_count;
  if v_rows = 1 then
    return true;
  end if;

  -- A replayed sequence is idempotent only when its event identity is unchanged.
  return exists (
    select 1 from public.engine_run_events e
     where e.engine_run_id = p_run_id
       and e.event_seq = p_event_seq
       and e.event_name = p_event_name
       and e.event_timestamp is not distinct from p_event_timestamp
  );
end;
$$;

revoke all on function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision)
  from public, anon, authenticated;
grant execute on function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision)
  to service_role;

comment on table public.engine_run_events is
  'Owner-readable, service-written allow-listed engine progress metadata. Never stores prompts, reasoning, tool arguments, previews, or outputs.';
