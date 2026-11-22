-- Persist a strictly allow-listed set of subagent lifecycle counters/identifiers.
-- Never store subagent goals, summaries, prompts, tool arguments, or output text.

alter table public.engine_run_events
  add column metadata jsonb not null default '{}'::jsonb;

alter table public.engine_run_events
  add constraint engine_run_events_metadata_object_check
  check (jsonb_typeof(metadata) = 'object') not valid;

drop function public.append_engine_run_event(uuid,uuid,uuid,text,bigint,double precision,text,text);

create function public.append_engine_run_event(
  p_run_id uuid,
  p_step_id uuid,
  p_lease_token uuid,
  p_event_name text,
  p_event_seq bigint default null,
  p_event_timestamp double precision default null,
  p_approval_request_id text default null,
  p_approval_choice text default null,
  p_metadata jsonb default '{}'::jsonb
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
       and (p_approval_choice is null or p_approval_choice not in ('once', 'deny')) then
      raise exception 'invalid_engine_run_approval_choice';
    end if;
  elsif p_approval_request_id is not null or p_approval_choice is not null then
    raise exception 'unexpected_engine_run_approval_metadata';
  end if;

  if p_metadata is null
     or jsonb_typeof(p_metadata) <> 'object'
     or octet_length(p_metadata::text) > 2048 then
    raise exception 'invalid_engine_run_event_metadata';
  end if;
  if exists (
    select 1 from jsonb_object_keys(p_metadata) as k
     where k not in (
       'subagent_id', 'delegation_id', 'parent_id', 'child_session_id',
       'status', 'task_index', 'task_count', 'depth', 'tool_count',
       'input_tokens', 'output_tokens', 'duration_seconds'
     )
  ) then
    raise exception 'unexpected_engine_run_event_metadata';
  end if;
  if p_event_name not in ('subagent.start', 'subagent.complete')
     and p_metadata <> '{}'::jsonb then
    raise exception 'unexpected_engine_run_event_metadata';
  end if;
  if p_event_name in ('subagent.start', 'subagent.complete') then
    if not (p_metadata ? 'subagent_id')
       or jsonb_typeof(p_metadata->'subagent_id') <> 'string'
       or length(p_metadata->>'subagent_id') not between 1 and 128
       or p_metadata->>'subagent_id' !~ '^[A-Za-z0-9_-]{1,128}$' then
      raise exception 'invalid_engine_run_subagent_id';
    end if;
  end if;

  if p_metadata ? 'delegation_id'
     and (jsonb_typeof(p_metadata->'delegation_id') <> 'string'
       or length(p_metadata->>'delegation_id') not between 1 and 128
       or p_metadata->>'delegation_id' !~ '^[A-Za-z0-9_-]{1,128}$') then
    raise exception 'invalid_engine_run_delegation_id';
  end if;
  if p_metadata ? 'parent_id'
     and (jsonb_typeof(p_metadata->'parent_id') <> 'string'
       or length(p_metadata->>'parent_id') not between 1 and 128
       or p_metadata->>'parent_id' !~ '^[A-Za-z0-9_-]{1,128}$') then
    raise exception 'invalid_engine_run_parent_id';
  end if;
  if p_metadata ? 'child_session_id'
     and (jsonb_typeof(p_metadata->'child_session_id') <> 'string'
       or length(p_metadata->>'child_session_id') not between 1 and 128
       or p_metadata->>'child_session_id' !~ '^[A-Za-z0-9_-]{1,128}$') then
    raise exception 'invalid_engine_run_child_session_id';
  end if;
  if p_metadata ? 'status'
     and (jsonb_typeof(p_metadata->'status') <> 'string'
       or p_metadata->>'status' not in ('started','running','completed','failed','cancelled')) then
    raise exception 'invalid_engine_run_subagent_status';
  end if;

  if exists (
    select 1
      from jsonb_each(p_metadata) e
     where e.key in ('task_index','task_count','depth','tool_count','input_tokens','output_tokens')
       and (
         jsonb_typeof(e.value) <> 'number'
         or (e.value #>> '{}') !~ '^[0-9]{1,10}$'
         or (e.value #>> '{}')::numeric > 1000000000
       )
  ) then
    raise exception 'invalid_engine_run_subagent_counter';
  end if;
  if p_metadata ? 'duration_seconds'
     and (
       jsonb_typeof(p_metadata->'duration_seconds') <> 'number'
       or (p_metadata->>'duration_seconds')::numeric < 0
       or (p_metadata->>'duration_seconds')::numeric > 86400
     ) then
    raise exception 'invalid_engine_run_subagent_duration';
  end if;

  select r.user_id, r.task_id
    into v_user_id, v_task_id
    from public.engine_runs r
    join public.task_steps s
      on s.id = r.step_id
     and s.task_id = r.task_id
     and s.user_id = r.user_id
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
    approval_request_id, approval_choice, metadata
  ) values (
    p_run_id, v_task_id, v_user_id, p_event_name, p_event_seq, p_event_timestamp,
    p_approval_request_id, p_approval_choice, p_metadata
  )
  on conflict (engine_run_id, event_seq) where event_seq is not null do nothing;

  get diagnostics v_rows = row_count;
  if v_rows = 1 then
    return true;
  end if;

  return exists (
    select 1
      from public.engine_run_events e
     where e.engine_run_id = p_run_id
       and e.event_seq = p_event_seq
       and e.event_name = p_event_name
       and e.event_timestamp is not distinct from p_event_timestamp
       and e.approval_request_id is not distinct from p_approval_request_id
       and e.approval_choice is not distinct from p_approval_choice
       and e.metadata = p_metadata
  );
end;
$$;

revoke all on function public.append_engine_run_event(
  uuid,uuid,uuid,text,bigint,double precision,text,text,jsonb
) from public, anon, authenticated;
grant execute on function public.append_engine_run_event(
  uuid,uuid,uuid,text,bigint,double precision,text,text,jsonb
) to service_role;

comment on column public.engine_run_events.metadata is
  'Bounded allow-listed subagent identifiers and counters only; never stores goals, summaries, prompts, tool input, or output.';
