-- Add only opaque approval identity and a bounded decision to the existing
-- metadata-only event ledger. Never persist command/description/tool payloads.
alter table public.engine_run_events
  add column approval_request_id text,
  add column approval_choice text;

alter table public.engine_run_events
  add constraint engine_run_events_approval_metadata_check check (
    (
      event_name = 'approval.request'
      and approval_request_id is not null
      and length(approval_request_id) between 1 and 256
      and approval_choice is null
    )
    or (
      event_name = 'approval.responded'
      and approval_request_id is not null
      and length(approval_request_id) between 1 and 256
      and approval_choice in ('once', 'deny')
    )
    or (
      event_name not in ('approval.request', 'approval.responded')
      and approval_request_id is null
      and approval_choice is null
    )
  ) not valid;

alter table public.engine_run_events
  add constraint engine_run_events_approval_request_ascii_check check (
    approval_request_id is null
    or approval_request_id ~ '^[A-Za-z0-9_.:@-]{1,256}
create index engine_run_events_approval_lookup_idx
  on public.engine_run_events(engine_run_id, approval_request_id, event_name)
  where approval_request_id is not null;

drop function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision);

create function public.append_engine_run_event(
  p_run_id uuid,
  p_step_id uuid,
  p_lease_token uuid,
  p_event_name text,
  p_event_seq bigint default null,
  p_event_timestamp double precision default null,
  p_approval_request_id text default null,
  p_approval_choice text default null
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
  if p_event_name in ('approval.request', 'approval.responded') then
    if p_approval_request_id is null
       or length(p_approval_request_id) not between 1 and 256
       or p_approval_request_id !~ '^[A-Za-z0-9_.:@-]{1,256}$' then
      raise exception 'invalid_engine_run_approval_request_id';
    end if;
    if p_event_name = 'approval.request' and p_approval_choice is not null then
      raise exception 'invalid_engine_run_approval_choice';
    end if;
    if p_event_name = 'approval.responded'
       and p_approval_choice not in ('once', 'deny') then
      raise exception 'invalid_engine_run_approval_choice';
    end if;
  elsif p_approval_request_id is not null or p_approval_choice is not null then
    raise exception 'unexpected_engine_run_approval_metadata';
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
    engine_run_id, task_id, user_id, event_name, event_seq, event_timestamp,
    approval_request_id, approval_choice
  ) values (
    p_run_id, v_task_id, v_user_id, p_event_name, p_event_seq, p_event_timestamp,
    p_approval_request_id, p_approval_choice
  )
  on conflict (engine_run_id, event_seq) where event_seq is not null do nothing;

  get diagnostics v_rows = row_count;
  if v_rows = 1 then
    return true;
  end if;

  return exists (
    select 1 from public.engine_run_events e
     where e.engine_run_id = p_run_id
       and e.event_seq = p_event_seq
       and e.event_name = p_event_name
       and e.event_timestamp is not distinct from p_event_timestamp
       and e.approval_request_id is not distinct from p_approval_request_id
       and e.approval_choice is not distinct from p_approval_choice
  );
end;
$$;

revoke all on function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision,text,text)
  from public, anon, authenticated;
grant execute on function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision,text,text)
  to service_role;

comment on column public.engine_run_events.approval_request_id is
  'Opaque upstream request identity only; never approval prompt or command text.';
comment on column public.engine_run_events.approval_choice is
  'Only once or deny; persistent/session grants are not exposed by SULY.';

  ) not valid;

create index engine_run_events_approval_lookup_idx
  on public.engine_run_events(engine_run_id, approval_request_id, event_name)
  where approval_request_id is not null;

drop function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision);

create function public.append_engine_run_event(
  p_run_id uuid,
  p_step_id uuid,
  p_lease_token uuid,
  p_event_name text,
  p_event_seq bigint default null,
  p_event_timestamp double precision default null,
  p_approval_request_id text default null,
  p_approval_choice text default null
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
  if p_event_name in ('approval.request', 'approval.responded') then
    if p_approval_request_id is null
       or length(p_approval_request_id) not between 1 and 256
       or p_approval_request_id !~ '^[A-Za-z0-9_.:@-]{1,256}$' then
      raise exception 'invalid_engine_run_approval_request_id';
    end if;
    if p_event_name = 'approval.request' and p_approval_choice is not null then
      raise exception 'invalid_engine_run_approval_choice';
    end if;
    if p_event_name = 'approval.responded'
       and p_approval_choice not in ('once', 'deny') then
      raise exception 'invalid_engine_run_approval_choice';
    end if;
  elsif p_approval_request_id is not null or p_approval_choice is not null then
    raise exception 'unexpected_engine_run_approval_metadata';
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
    engine_run_id, task_id, user_id, event_name, event_seq, event_timestamp,
    approval_request_id, approval_choice
  ) values (
    p_run_id, v_task_id, v_user_id, p_event_name, p_event_seq, p_event_timestamp,
    p_approval_request_id, p_approval_choice
  )
  on conflict (engine_run_id, event_seq) where event_seq is not null do nothing;

  get diagnostics v_rows = row_count;
  if v_rows = 1 then
    return true;
  end if;

  return exists (
    select 1 from public.engine_run_events e
     where e.engine_run_id = p_run_id
       and e.event_seq = p_event_seq
       and e.event_name = p_event_name
       and e.event_timestamp is not distinct from p_event_timestamp
       and e.approval_request_id is not distinct from p_approval_request_id
       and e.approval_choice is not distinct from p_approval_choice
  );
end;
$$;

revoke all on function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision,text,text)
  from public, anon, authenticated;
grant execute on function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision,text,text)
  to service_role;

comment on column public.engine_run_events.approval_request_id is
  'Opaque upstream request identity only; never approval prompt or command text.';
comment on column public.engine_run_events.approval_choice is
  'Only once or deny; persistent/session grants are not exposed by SULY.';
