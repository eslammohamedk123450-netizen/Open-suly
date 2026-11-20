-- Durable, owner-readable ledger for isolated engine attempts.
create table public.engine_runs (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null,
  step_id uuid not null references public.task_steps(id) on delete cascade,
  user_id uuid not null,
  attempt_count integer not null check (attempt_count between 1 and 10),
  engine_id text not null check (char_length(engine_id) between 2 and 63),
  status text not null default 'running'
    check (status in ('running','succeeded','failed','cancelled')),
  error_code text check (error_code is null or char_length(error_code) <= 80),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint engine_runs_step_owner_fkey
    foreign key (task_id, user_id) references public.tasks(id, user_id) on delete cascade,
  unique (step_id, attempt_count),
  check ((status = 'running') = (completed_at is null))
);

create index engine_runs_user_created_idx
  on public.engine_runs(user_id, created_at desc);
create index engine_runs_task_created_idx
  on public.engine_runs(task_id, created_at);

alter table public.engine_runs enable row level security;
create policy engine_runs_select_own on public.engine_runs
  for select to authenticated using ((select auth.uid()) = user_id);
grant select on public.engine_runs to authenticated;
grant all on public.engine_runs to service_role;

create or replace function public.start_engine_run(
  p_step_id uuid,
  p_lease_token uuid,
  p_engine_id text
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_step public.task_steps%rowtype;
  v_run_id uuid;
begin
  if p_engine_id is null or char_length(p_engine_id) not between 2 and 63 then
    raise exception 'invalid_engine_id';
  end if;

  select * into v_step
    from public.task_steps
   where id = p_step_id
     and status = 'running'
     and lease_token = p_lease_token
     and lease_expires_at > now()
   for update;

  if not found then
    raise exception 'engine_run_lease_invalid';
  end if;

  if exists (
    select 1 from public.tasks
     where id = v_step.task_id and cancel_requested_at is not null
  ) then
    raise exception 'engine_run_task_cancelled';
  end if;

  insert into public.engine_runs(task_id, step_id, user_id, attempt_count, engine_id)
  values (v_step.task_id, v_step.id, v_step.user_id, v_step.attempt_count, p_engine_id)
  on conflict (step_id, attempt_count) do update
    set updated_at = now()
    where public.engine_runs.status = 'running'
  returning id into v_run_id;

  if v_run_id is null then
    raise exception 'engine_run_attempt_already_finished';
  end if;
  return v_run_id;
end;
$$;

create or replace function public.finish_engine_run(
  p_run_id uuid,
  p_lease_token uuid,
  p_status text,
  p_error_code text default null
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rows integer;
begin
  if p_status is null or p_status not in ('succeeded','failed','cancelled') then
    raise exception 'invalid_engine_run_terminal_status';
  end if;

  update public.engine_runs r
     set status = case
           when t.cancel_requested_at is not null then 'cancelled'
           else p_status end,
         error_code = case
           when t.cancel_requested_at is not null then null
           when p_status = 'failed' then left(coalesce(nullif(btrim(p_error_code),''),'engine_failed'),80)
           else null end,
         completed_at = now(),
         updated_at = now()
    from public.task_steps s
    join public.tasks t on t.id = s.task_id
   where r.id = p_run_id
     and s.id = r.step_id
     and s.status = 'running'
     and s.lease_token = p_lease_token
     and s.lease_expires_at > now()
     and r.status = 'running'
     and s.task_id = r.task_id
     and s.user_id = r.user_id;
  get diagnostics v_rows = row_count;
  return v_rows = 1;
end;
$$;

revoke all on function public.start_engine_run(uuid,uuid,text) from public, anon, authenticated;
revoke all on function public.finish_engine_run(uuid,uuid,text,text) from public, anon, authenticated;
grant execute on function public.start_engine_run(uuid,uuid,text) to service_role;
grant execute on function public.finish_engine_run(uuid,uuid,text,text) to service_role;

comment on table public.engine_runs is
  'Owner-readable, server-written execution ledger for each durable task-step engine attempt. No prompt, secret, or provider payload is stored.';
