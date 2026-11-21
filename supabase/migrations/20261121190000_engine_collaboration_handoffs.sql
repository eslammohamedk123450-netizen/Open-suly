-- Durable, owner-readable audit metadata for cross-engine handoffs.
-- Payloads and secrets are never stored here; only hashes, engine identities,
-- bounded budgets and lifecycle state cross the handoff ledger.

create table public.engine_handoffs (
  id uuid primary key,
  task_id uuid not null,
  user_id uuid not null,
  source_step_id uuid not null references public.task_steps(id) on delete cascade,
  target_step_id uuid not null references public.task_steps(id) on delete cascade,
  target_attempt_count smallint not null check (target_attempt_count between 1 and 10),
  source_run_id uuid not null references public.engine_runs(id) on delete cascade,
  target_run_id uuid references public.engine_runs(id) on delete set null,
  source_engine_id text not null check (source_engine_id in ('hermes-agent', 'opencode')),
  target_engine_id text not null check (target_engine_id in ('hermes-agent', 'opencode')),
  capability text not null check (capability ~ '^[a-z][a-z0-9_.-]{1,95}$'),
  depth smallint not null default 1 check (depth between 1 and 3),
  max_child_tasks smallint not null default 1 check (max_child_tasks between 1 and 8),
  max_parallel_children smallint not null default 1 check (max_parallel_children between 1 and 2),
  max_runtime_seconds integer not null default 300 check (max_runtime_seconds between 1 and 1800),
  input_sha256 text not null check (input_sha256 ~ '^[0-9a-f]{64}$'),
  input_bytes integer not null check (input_bytes between 1 and 64000),
  output_sha256 text check (output_sha256 is null or output_sha256 ~ '^[0-9a-f]{64}$'),
  output_bytes integer check (output_bytes is null or output_bytes between 0 and 64000),
  status text not null default 'running'
    check (status in ('running', 'completed', 'failed', 'cancelled')),
  error_code text check (error_code is null or char_length(error_code) <= 80),
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint engine_handoffs_task_owner_fkey
    foreign key (task_id, user_id)
    references public.tasks(id, user_id) on delete cascade,
  constraint engine_handoffs_distinct_engines_check
    check (source_engine_id <> target_engine_id),
  constraint engine_handoffs_parallel_budget_check
    check (max_parallel_children <= max_child_tasks),
  constraint engine_handoffs_terminal_timestamp_check
    check ((status = 'running') = (completed_at is null)),
  unique (target_step_id, target_attempt_count)
);

create index engine_handoffs_user_created_idx
  on public.engine_handoffs(user_id, created_at desc);
create index engine_handoffs_task_created_idx
  on public.engine_handoffs(task_id, created_at desc);
create index engine_handoffs_source_run_idx
  on public.engine_handoffs(source_run_id);
create index engine_handoffs_target_run_idx
  on public.engine_handoffs(target_run_id)
  where target_run_id is not null;

alter table public.engine_handoffs enable row level security;
revoke all on table public.engine_handoffs from anon, authenticated;
grant select on table public.engine_handoffs to authenticated;
grant all on table public.engine_handoffs to service_role;

create policy engine_handoffs_select_own
  on public.engine_handoffs
  for select to authenticated
  using ((select auth.uid()) = user_id);

create function public.start_engine_handoff(
  p_handoff_id uuid,
  p_task_id uuid,
  p_user_id uuid,
  p_source_step_id uuid,
  p_target_step_id uuid,
  p_target_attempt_count integer,
  p_lease_token uuid,
  p_source_run_id uuid,
  p_source_engine_id text,
  p_target_engine_id text,
  p_capability text,
  p_depth integer,
  p_max_child_tasks integer,
  p_max_parallel_children integer,
  p_max_runtime_seconds integer,
  p_input_sha256 text,
  p_input_bytes integer
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_target public.task_steps%rowtype;
  v_source public.task_steps%rowtype;
begin
  if p_handoff_id is null
     or p_source_engine_id not in ('hermes-agent', 'opencode')
     or p_target_engine_id not in ('hermes-agent', 'opencode')
     or p_source_engine_id = p_target_engine_id
     or p_capability is null
     or p_capability !~ '^[a-z][a-z0-9_.-]{1,95}$'
     or p_depth is null or p_depth not between 1 and 3
     or p_target_attempt_count is null or p_target_attempt_count not between 1 and 10
     or p_max_child_tasks not between 1 and 8
     or p_max_parallel_children not between 1 and 2
     or p_max_parallel_children > p_max_child_tasks
     or p_max_runtime_seconds not between 1 and 1800
     or p_input_sha256 is null
     or p_input_sha256 !~ '^[0-9a-f]{64}$'
     or p_input_bytes not between 1 and 64000 then
    raise exception 'invalid_engine_handoff_contract' using errcode = '22023';
  end if;

  select s.*
    into v_target
    from public.task_steps s
   where s.id = p_target_step_id
     and s.task_id = p_task_id
     and s.user_id = p_user_id
     and s.status = 'running'
     and s.lease_token = p_lease_token
     and s.lease_expires_at > now()
   for update;

  if not found then
    return false;
  end if;

  select s.*
    into v_source
    from public.task_steps s
   where s.id = p_source_step_id
     and s.task_id = p_task_id
     and s.user_id = p_user_id
     and s.status = 'completed';

  if not found
     or not (v_target.depends_on @> pg_catalog.jsonb_build_array(v_source.step_key)) then
    raise exception 'engine_handoff_source_not_completed_dependency' using errcode = '55000';
  end if;

  if not exists (
    select 1
      from public.engine_runs r
     where r.id = p_source_run_id
       and r.task_id = p_task_id
       and r.step_id = p_source_step_id
       and r.user_id = p_user_id
       and r.engine_id = p_source_engine_id
       and r.status = 'succeeded'
  ) then
    raise exception 'engine_handoff_source_run_mismatch' using errcode = '55000';
  end if;

  insert into public.engine_handoffs (
    id, task_id, user_id, source_step_id, target_step_id, target_attempt_count, source_run_id,
    source_engine_id, target_engine_id, capability, depth,
    max_child_tasks, max_parallel_children, max_runtime_seconds,
    input_sha256, input_bytes
  ) values (
    p_handoff_id, p_task_id, p_user_id, p_source_step_id, p_target_step_id,
    p_target_attempt_count, p_source_run_id, p_source_engine_id, p_target_engine_id, p_capability,
    p_depth, p_max_child_tasks, p_max_parallel_children, p_max_runtime_seconds,
    p_input_sha256, p_input_bytes
  )
  on conflict (target_step_id, target_attempt_count) do nothing;

  return exists (
    select 1 from public.engine_handoffs h
     where h.id = p_handoff_id
       and h.task_id = p_task_id
       and h.user_id = p_user_id
       and h.source_step_id = p_source_step_id
       and h.target_step_id = p_target_step_id
       and h.target_attempt_count = p_target_attempt_count
       and h.source_run_id = p_source_run_id
       and h.status = 'running'
  );
end;
$$;

create function public.finish_engine_handoff(
  p_handoff_id uuid,
  p_target_step_id uuid,
  p_lease_token uuid,
  p_target_run_id uuid,
  p_status text,
  p_output_sha256 text,
  p_output_bytes integer,
  p_error_code text default null
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_handoff public.engine_handoffs%rowtype;
begin
  if p_status not in ('completed', 'failed', 'cancelled')
     or (p_output_sha256 is not null and p_output_sha256 !~ '^[0-9a-f]{64}$')
     or (p_output_bytes is not null and p_output_bytes not between 0 and 64000)
     or (p_error_code is not null and char_length(p_error_code) > 80) then
    raise exception 'invalid_engine_handoff_result' using errcode = '22023';
  end if;
  if p_status = 'completed'
     and (p_target_run_id is null or p_output_sha256 is null or p_output_bytes is null) then
    raise exception 'completed_engine_handoff_requires_result_digest' using errcode = '22023';
  end if;

  select h.*
    into v_handoff
    from public.engine_handoffs h
   where h.id = p_handoff_id
     and h.target_step_id = p_target_step_id
     and h.status = 'running'
   for update;

  if not found then
    return false;
  end if;

  if not exists (
    select 1
      from public.task_steps s
     where s.id = p_target_step_id
       and s.task_id = v_handoff.task_id
       and s.user_id = v_handoff.user_id
       and s.status = 'running'
       and s.lease_token = p_lease_token
       and s.lease_expires_at > now()
  ) then
    return false;
  end if;

  if p_target_run_id is not null and not exists (
    select 1
      from public.engine_runs r
     where r.id = p_target_run_id
       and r.task_id = v_handoff.task_id
       and r.step_id = p_target_step_id
       and r.user_id = v_handoff.user_id
       and r.engine_id = v_handoff.target_engine_id
       and (
         (p_status = 'completed' and r.status = 'succeeded')
         or (p_status = 'failed' and r.status = 'failed')
         or (p_status = 'cancelled' and r.status = 'cancelled')
       )
  ) then
    raise exception 'engine_handoff_target_run_mismatch' using errcode = '55000';
  end if;

  update public.engine_handoffs
     set target_run_id = p_target_run_id,
         status = p_status,
         output_sha256 = p_output_sha256,
         output_bytes = p_output_bytes,
         error_code = p_error_code,
         completed_at = now()
   where id = p_handoff_id
     and status = 'running';

  return true;
end;
$$;

revoke all on function public.start_engine_handoff(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,integer,integer,integer,integer,text,integer
) from public, anon, authenticated;
revoke all on function public.finish_engine_handoff(
  uuid,uuid,uuid,uuid,text,text,integer,text
) from public, anon, authenticated;
grant execute on function public.start_engine_handoff(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,integer,integer,integer,integer,text,integer
) to service_role;
grant execute on function public.finish_engine_handoff(
  uuid,uuid,uuid,uuid,text,text,integer,text
) to service_role;

comment on table public.engine_handoffs is
  'Owner-readable metadata-only ledger for explicit sequential cross-engine handoffs. Prompts, raw outputs, workspace bytes and credentials are intentionally excluded.';
