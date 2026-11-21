-- Durable, owner-approved cross-engine delegation lifecycle.
-- Child tasks are ordinary SULY DAG tasks; engine runtimes remain isolated.

alter table public.engine_collaboration_handoffs
  add column if not exists input_payload jsonb not null default '{}'::jsonb;

alter table public.engine_collaboration_handoffs
  add constraint engine_collaboration_input_payload_check
  check (
    jsonb_typeof(input_payload) = 'object'
    and octet_length(input_payload::text) <= 64000
    and (input_payload - array['prompt','title']) = '{}'::jsonb
    and jsonb_typeof(input_payload->'prompt') = 'string'
    and char_length(btrim(input_payload->>'prompt')) between 1 and 20000
    and (
      not (input_payload ? 'title')
      or (
        jsonb_typeof(input_payload->'title') = 'string'
        and char_length(btrim(input_payload->>'title')) between 1 and 120
      )
    )
  ) not valid;

create unique index if not exists engine_collaboration_child_task_uidx
  on public.engine_collaboration_handoffs(child_task_id)
  where child_task_id is not null;

create or replace function public.create_engine_collaboration_handoff(
  p_parent_task_id uuid,
  p_parent_run_id uuid,
  p_target_engine text,
  p_capability text,
  p_idempotency_key text,
  p_input_payload jsonb,
  p_max_child_tasks smallint default 1,
  p_max_parallel_children smallint default 1,
  p_max_runtime_seconds integer default 300,
  p_max_input_bytes integer default 64000
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_task public.tasks%rowtype;
  v_run public.engine_runs%rowtype;
  v_existing public.engine_collaboration_handoffs%rowtype;
  v_source_engine text;
  v_depth smallint;
  v_count integer;
  v_child_budget smallint;
  v_input_bytes integer;
  v_handoff_id uuid;
begin
  if p_target_engine not in ('hermes-agent','opencode')
     or p_capability is null
     or p_capability !~ '^[a-z][a-z0-9_.-]{1,95}$'
     or p_idempotency_key is null
     or length(p_idempotency_key) not between 16 and 128
     or p_idempotency_key !~ '^[A-Za-z0-9_-]+$'
     or p_max_child_tasks not between 1 and 8
     or p_max_parallel_children not between 1 and 2
     or p_max_runtime_seconds not between 1 and 1800
     or p_max_input_bytes not between 1 and 64000 then
    raise exception 'collaboration_request_invalid';
  end if;

  if p_input_payload is null
     or jsonb_typeof(p_input_payload) <> 'object'
     or (p_input_payload - array['prompt','title']) <> '{}'::jsonb
     or jsonb_typeof(p_input_payload->'prompt') <> 'string'
     or char_length(btrim(p_input_payload->>'prompt')) not between 1 and 20000
     or octet_length(p_input_payload::text) > p_max_input_bytes
     or octet_length(p_input_payload::text) > 64000 then
    raise exception 'collaboration_payload_invalid';
  end if;
  if p_input_payload ? 'title'
     and (
       jsonb_typeof(p_input_payload->'title') <> 'string'
       or char_length(btrim(p_input_payload->>'title')) not between 1 and 120
     ) then
    raise exception 'collaboration_title_invalid';
  end if;
  v_input_bytes := octet_length(p_input_payload::text);

  -- Lock parent task and run so concurrent submissions cannot race the parent state.
  select * into v_task
    from public.tasks
   where id = p_parent_task_id
   for update;
  if not found then
    raise exception 'collaboration_parent_task_not_found';
  end if;
  if v_task.status <> 'running' or v_task.cancel_requested_at is not null then
    raise exception 'collaboration_parent_task_not_running';
  end if;

  select * into v_run
    from public.engine_runs
   where id = p_parent_run_id
     and task_id = p_parent_task_id
     and user_id = v_task.user_id
   for update;
  if not found or v_run.status <> 'running' then
    raise exception 'collaboration_parent_run_not_running';
  end if;
  v_source_engine := v_run.engine_id;

  if v_source_engine = p_target_engine then
    raise exception 'collaboration_same_engine_handoff_rejected';
  end if;
  if p_target_engine = 'opencode'
     and (
       p_capability not in ('code.edit','code.review','code.test','code.repository')
       or v_task.project_id is null
     ) then
    raise exception 'collaboration_target_capability_not_supported';
  end if;
  if p_target_engine = 'hermes-agent'
     and p_capability not in ('agent.general','research','research.summarize') then
    raise exception 'collaboration_target_capability_not_supported';
  end if;

  -- A delegation chain may be at most three hops deep.
  select (coalesce(max(h.depth), 0) + 1)::smallint
    into v_depth
    from public.engine_collaboration_handoffs h
   where h.child_task_id = p_parent_task_id
     and h.user_id = v_task.user_id;
  if v_depth not between 1 and 3 then
    raise exception 'collaboration_depth_exceeded';
  end if;

  -- A stable owner idempotency key prevents duplicate handoff records.
  select * into v_existing
    from public.engine_collaboration_handoffs
   where user_id = v_task.user_id
     and idempotency_key = p_idempotency_key
   for update;
  if found then
    if v_existing.parent_task_id <> p_parent_task_id
       or v_existing.parent_run_id <> p_parent_run_id
       or v_existing.target_engine <> p_target_engine
       or v_existing.capability <> p_capability
       or v_existing.input_payload <> p_input_payload then
      raise exception 'collaboration_idempotency_conflict';
    end if;
    return v_existing.id;
  end if;

  select count(*)::integer, min(h.max_child_tasks)
    into v_count, v_child_budget
    from public.engine_collaboration_handoffs h
   where h.parent_run_id = p_parent_run_id
     and h.user_id = v_task.user_id
     and h.status not in ('rejected','cancelled');
  if v_count >= least(coalesce(v_child_budget, p_max_child_tasks), p_max_child_tasks) then
    raise exception 'collaboration_child_budget_exceeded';
  end if;

  insert into public.engine_collaboration_handoffs (
    parent_task_id, parent_run_id, user_id, source_engine, target_engine,
    capability, status, depth, max_child_tasks, max_parallel_children,
    max_runtime_seconds, max_input_bytes, idempotency_key, input_payload
  ) values (
    p_parent_task_id, p_parent_run_id, v_task.user_id, v_source_engine, p_target_engine,
    p_capability, 'pending_approval', v_depth, p_max_child_tasks, p_max_parallel_children,
    p_max_runtime_seconds, p_max_input_bytes, p_idempotency_key, p_input_payload
  )
  returning id into v_handoff_id;

  insert into public.engine_collaboration_events (
    handoff_id, user_id, sequence, event_type, status, metadata
  ) values (
    v_handoff_id, v_task.user_id, 1, 'handoff.created', 'pending', '{}'::jsonb
  );

  return v_handoff_id;
end;
$$;

create or replace function public.approve_engine_collaboration_handoff(
  p_handoff_id uuid,
  p_user_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_handoff public.engine_collaboration_handoffs%rowtype;
  v_parent public.tasks%rowtype;
  v_parent_run public.engine_runs%rowtype;
  v_child_id uuid;
  v_child_key text;
  v_step_key text;
  v_prompt text;
  v_title text;
  v_operation text;
  v_step_input jsonb;
  v_plan jsonb;
  v_count integer;
  v_parallel_count integer;
  v_child_budget smallint;
  v_parallel_budget smallint;
  v_seq bigint;
begin
  select * into v_handoff
    from public.engine_collaboration_handoffs
   where id = p_handoff_id
     and user_id = p_user_id
   for update;
  if not found then
    raise exception 'collaboration_handoff_not_found';
  end if;
  if v_handoff.status <> 'pending_approval' then
    raise exception 'collaboration_handoff_not_pending';
  end if;

  select * into v_parent
    from public.tasks
   where id = v_handoff.parent_task_id
     and user_id = p_user_id
   for update;
  if not found or v_parent.status <> 'running' or v_parent.cancel_requested_at is not null then
    raise exception 'collaboration_parent_task_not_running';
  end if;

  select * into v_parent_run
    from public.engine_runs
   where id = v_handoff.parent_run_id
     and task_id = v_parent.id
     and user_id = p_user_id
   for update;
  if not found or v_parent_run.status <> 'running'
     or v_parent_run.engine_id <> v_handoff.source_engine then
    raise exception 'collaboration_parent_run_not_running';
  end if;

  select count(*)::integer,
         count(*) filter (where h.status in ('approved','running'))::integer,
         min(h.max_child_tasks),
         min(h.max_parallel_children)
    into v_count, v_parallel_count, v_child_budget, v_parallel_budget
    from public.engine_collaboration_handoffs h
   where h.parent_run_id = v_handoff.parent_run_id
     and h.user_id = p_user_id
     and h.status not in ('rejected','cancelled');
  if v_count > least(coalesce(v_child_budget, v_handoff.max_child_tasks), v_handoff.max_child_tasks) then
    raise exception 'collaboration_child_budget_exceeded';
  end if;
  if v_parallel_count >= least(coalesce(v_parallel_budget, v_handoff.max_parallel_children), v_handoff.max_parallel_children) then
    raise exception 'collaboration_parallel_limit_reached';
  end if;

  v_prompt := v_handoff.input_payload->>'prompt';
  v_title := coalesce(nullif(btrim(v_handoff.input_payload->>'title'), ''), 'SULY delegated task');
  if v_handoff.target_engine = 'opencode' then
    if v_parent.project_id is null then
      raise exception 'collaboration_project_required';
    end if;
    v_operation := 'opencode.task.run';
    v_step_input := jsonb_build_object(
      'operation', v_operation,
      'project_id', v_parent.project_id,
      'prompt', v_prompt,
      'title', v_title
    );
  elsif v_handoff.target_engine = 'hermes-agent' then
    v_operation := 'hermes.agent.turn';
    v_step_input := jsonb_build_object(
      'operation', v_operation,
      'prompt', v_prompt
    );
  else
    raise exception 'collaboration_target_engine_not_supported';
  end if;

  v_child_id := gen_random_uuid();
  v_child_key := 'collab-' || replace(v_handoff.id::text, '-', '');
  v_step_key := 'handoff_' || left(replace(v_handoff.id::text, '-', ''), 20);
  v_plan := jsonb_build_array(jsonb_build_object(
    'step_key', v_step_key,
    'title', v_title,
    'description', 'SULY-approved isolated cross-engine delegated task.',
    'depends_on', '[]'::jsonb,
    'input', v_step_input
  ));

  insert into public.tasks (
    id, user_id, project_id, conversation_id, title, request, status,
    plan, idempotency_key, max_attempts, created_at, updated_at
  ) values (
    v_child_id, p_user_id, v_parent.project_id, v_parent.conversation_id,
    v_title, v_prompt, 'queued', v_plan, v_child_key, 3, now(), now()
  );

  insert into public.task_steps (
    task_id, user_id, step_key, title, description, step_order, depends_on, input
  ) values (
    v_child_id, p_user_id, v_step_key, v_title,
    'SULY-approved isolated cross-engine delegated task.', 0, '[]'::jsonb, v_step_input
  );

  update public.tasks
     set status = 'ready'
   where id = v_child_id
     and user_id = p_user_id;

  update public.engine_collaboration_handoffs
     set status = 'approved',
         approved_at = now(),
         updated_at = now()
   where id = v_handoff.id;

  select coalesce(max(sequence), 0) + 1 into v_seq
    from public.engine_collaboration_events
   where handoff_id = v_handoff.id;
  insert into public.engine_collaboration_events (
    handoff_id, user_id, sequence, event_type, status, metadata
  ) values (
    v_handoff.id, p_user_id, v_seq, 'handoff.approved', 'approved', '{}'::jsonb
  );

  update public.engine_collaboration_handoffs
     set status = 'running',
         child_task_id = v_child_id,
         started_at = now(),
         updated_at = now()
   where id = v_handoff.id;

  insert into public.engine_collaboration_events (
    handoff_id, user_id, sequence, event_type, status, metadata
  ) values (
    v_handoff.id, p_user_id, v_seq + 1, 'handoff.started', 'running',
    jsonb_build_object('child_task_id', v_child_id)
  );

  return jsonb_build_object(
    'handoff_id', v_handoff.id,
    'child_task_id', v_child_id,
    'status', 'running',
    'target_engine', v_handoff.target_engine
  );
end;
$$;

create or replace function public.reject_engine_collaboration_handoff(
  p_handoff_id uuid,
  p_user_id uuid
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_handoff public.engine_collaboration_handoffs%rowtype;
  v_seq bigint;
begin
  select * into v_handoff
    from public.engine_collaboration_handoffs
   where id = p_handoff_id
     and user_id = p_user_id
   for update;
  if not found then
    return false;
  end if;
  if v_handoff.status <> 'pending_approval' then
    raise exception 'collaboration_handoff_not_pending';
  end if;

  update public.engine_collaboration_handoffs
     set status = 'rejected', finished_at = now(), updated_at = now()
   where id = p_handoff_id;

  select coalesce(max(sequence), 0) + 1 into v_seq
    from public.engine_collaboration_events
   where handoff_id = p_handoff_id;
  insert into public.engine_collaboration_events (
    handoff_id, user_id, sequence, event_type, status, metadata
  ) values (
    p_handoff_id, p_user_id, v_seq, 'review.rejected', null, '{}'::jsonb
  );
  return true;
end;
$$;

create or replace function public.cancel_engine_collaboration_handoff(
  p_handoff_id uuid,
  p_user_id uuid
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_handoff public.engine_collaboration_handoffs%rowtype;
  v_seq bigint;
begin
  select * into v_handoff
    from public.engine_collaboration_handoffs
   where id = p_handoff_id
     and user_id = p_user_id
   for update;
  if not found then
    return false;
  end if;

  if v_handoff.status = 'pending_approval' then
    update public.engine_collaboration_handoffs
       set status = 'cancelled', finished_at = now(), updated_at = now()
     where id = p_handoff_id;
  elsif v_handoff.status = 'running' and v_handoff.child_task_id is not null then
    update public.tasks
       set status = 'cancel_requested',
           cancel_requested_at = coalesce(cancel_requested_at, now())
     where id = v_handoff.child_task_id
       and user_id = p_user_id
       and status in ('queued','planning','ready','running','waiting_approval');
    return true;
  else
    raise exception 'collaboration_handoff_not_cancellable';
  end if;

  select coalesce(max(sequence), 0) + 1 into v_seq
    from public.engine_collaboration_events
   where handoff_id = p_handoff_id;
  insert into public.engine_collaboration_events (
    handoff_id, user_id, sequence, event_type, status, metadata
  ) values (
    p_handoff_id, p_user_id, v_seq, 'handoff.cancelled', 'cancelled', '{}'::jsonb
  );
  return true;
end;
$$;

create or replace function public.sync_engine_collaboration_child_task_status()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_handoff public.engine_collaboration_handoffs%rowtype;
  v_event text;
  v_seq bigint;
begin
  if new.status not in ('completed','failed','cancelled')
     or old.status = new.status then
    return new;
  end if;

  select * into v_handoff
    from public.engine_collaboration_handoffs h
   where h.child_task_id = new.id
     and h.user_id = new.user_id
     and h.status = 'running'
   for update;
  if not found then
    return new;
  end if;

  v_event := case new.status
    when 'completed' then 'handoff.completed'
    when 'cancelled' then 'handoff.cancelled'
    else 'handoff.failed'
  end;

  update public.engine_collaboration_handoffs
     set status = new.status,
         error_code = case when new.status = 'failed' then 'child_task_failed' else null end,
         finished_at = now(),
         updated_at = now()
   where id = v_handoff.id;

  select coalesce(max(sequence), 0) + 1 into v_seq
    from public.engine_collaboration_events
   where handoff_id = v_handoff.id;
  insert into public.engine_collaboration_events (
    handoff_id, user_id, sequence, event_type, status, metadata
  ) values (
    v_handoff.id, new.user_id, v_seq, v_event, new.status, '{}'::jsonb
  );
  return new;
end;
$$;

drop trigger if exists tasks_sync_engine_collaboration_child on public.tasks;
create trigger tasks_sync_engine_collaboration_child
  after update of status on public.tasks
  for each row
  execute function public.sync_engine_collaboration_child_task_status();

create or replace function public.cancel_engine_collaboration_children_on_parent_cancel()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.cancel_requested_at is null and new.cancel_requested_at is not null then
    update public.tasks child
       set status = 'cancel_requested',
           cancel_requested_at = coalesce(child.cancel_requested_at, now())
     where child.user_id = new.user_id
       and child.id in (
         select h.child_task_id
           from public.engine_collaboration_handoffs h
          where h.parent_task_id = new.id
            and h.user_id = new.user_id
            and h.status = 'running'
            and h.child_task_id is not null
       )
       and child.status in ('queued','planning','ready','running','waiting_approval');
  end if;
  return new;
end;
$$;

drop trigger if exists tasks_cancel_engine_collaboration_children on public.tasks;
create trigger tasks_cancel_engine_collaboration_children
  after update of cancel_requested_at on public.tasks
  for each row
  execute function public.cancel_engine_collaboration_children_on_parent_cancel();

revoke all on function public.create_engine_collaboration_handoff(
  uuid,uuid,text,text,text,jsonb,smallint,smallint,integer,integer
) from public, anon, authenticated;
revoke all on function public.approve_engine_collaboration_handoff(uuid,uuid)
  from public, anon, authenticated;
revoke all on function public.reject_engine_collaboration_handoff(uuid,uuid)
  from public, anon, authenticated;
revoke all on function public.cancel_engine_collaboration_handoff(uuid,uuid)
  from public, anon, authenticated;
revoke all on function public.sync_engine_collaboration_child_task_status()
  from public, anon, authenticated;
revoke all on function public.cancel_engine_collaboration_children_on_parent_cancel()
  from public, anon, authenticated;

grant execute on function public.create_engine_collaboration_handoff(
  uuid,uuid,text,text,text,jsonb,smallint,smallint,integer,integer
) to service_role;
grant execute on function public.approve_engine_collaboration_handoff(uuid,uuid)
  to service_role;
grant execute on function public.reject_engine_collaboration_handoff(uuid,uuid)
  to service_role;
grant execute on function public.cancel_engine_collaboration_handoff(uuid,uuid)
  to service_role;
grant execute on function public.sync_engine_collaboration_child_task_status()
  to service_role;
grant execute on function public.cancel_engine_collaboration_children_on_parent_cancel()
  to service_role;

comment on column public.engine_collaboration_handoffs.input_payload is
  'Owner-authorized bounded delegation input (prompt/title only); never includes credentials, model history, or raw tool state.';
comment on function public.approve_engine_collaboration_handoff(uuid,uuid) is
  'Atomically verifies a running parent lease context, records owner approval, creates one ordinary SULY child DAG task, and starts the handoff.';
