-- Durable outbox for SULY-controlled Hermes delegation proposals.
-- A completed Hermes step is the only source of a plan; delivery is retried
-- independently from task completion and uses the existing idempotent handoff RPC.

create table if not exists public.hermes_delegation_outbox (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null,
  step_id uuid not null unique references public.task_steps(id) on delete cascade,
  user_id uuid not null,
  parent_run_id uuid not null references public.engine_runs(id) on delete cascade,
  payload jsonb not null,
  status text not null default 'pending'
    check (status in ('pending','processing','submitted','failed')),
  attempt_count integer not null default 0 check (attempt_count between 0 and 20),
  available_at timestamptz not null default now(),
  lease_owner text,
  lease_token uuid,
  lease_expires_at timestamptz,
  result jsonb not null default '{}'::jsonb check (jsonb_typeof(result) = 'object'),
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint hermes_delegation_outbox_task_owner_fkey
    foreign key (task_id,user_id) references public.tasks(id,user_id) on delete cascade,
  constraint hermes_delegation_outbox_payload_check check (
    jsonb_typeof(payload) = 'object'
    and payload->>'schema_version' = '1'
    and case
      when jsonb_typeof(payload->'delegations') = 'array'
      then jsonb_array_length(payload->'delegations') between 1 and 8
      else false
    end
    and octet_length(payload::text) <= 64000
  ),
  constraint hermes_delegation_outbox_lease_check check (
    (lease_token is null) = (lease_expires_at is null)
    and (lease_token is null) = (lease_owner is null)
  )
);

create index if not exists hermes_delegation_outbox_claim_idx
  on public.hermes_delegation_outbox(status,available_at,created_at)
  where status in ('pending','processing');

alter table public.hermes_delegation_outbox enable row level security;
revoke all on table public.hermes_delegation_outbox from public,anon,authenticated;
grant all on table public.hermes_delegation_outbox to service_role;

create or replace function public.enqueue_completed_hermes_delegation_plan()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_run_id uuid;
  v_run public.engine_runs%rowtype;
  v_item jsonb;
begin
  if new.status <> 'completed' or old.status = 'completed'
     or new.input->>'operation' is distinct from 'hermes.agent.turn'
     or not (new.output ? 'delegation_plan') then
    return new;
  end if;

  if new.output->>'operation' is distinct from 'hermes.agent.turn'
     or new.output->>'engine' is distinct from 'hermes-agent'
     or jsonb_typeof(new.output->'delegation_plan') <> 'object'
     or new.output->'delegation_plan'->>'schema_version' <> '1'
     or (
       case
         when jsonb_typeof(new.output->'delegation_plan'->'delegations') = 'array'
         then jsonb_array_length(new.output->'delegation_plan'->'delegations') not between 1 and 8
         else true
       end
     )
     or octet_length((new.output->'delegation_plan')::text) > 64000 then
    raise exception 'hermes_delegation_plan_invalid' using errcode = '22023';
  end if;

  begin
    v_run_id := (new.output->>'engine_run_id')::uuid;
  exception when others then
    raise exception 'hermes_delegation_run_identity_invalid' using errcode = '22023';
  end;

  select * into v_run
    from public.engine_runs
   where id = v_run_id
     and step_id = new.id
     and task_id = new.task_id
     and user_id = new.user_id
     and engine_id = 'hermes-agent'
     and status = 'succeeded';
  if not found then
    raise exception 'hermes_delegation_source_run_invalid' using errcode = '55000';
  end if;

  for v_item in
    select value from jsonb_array_elements(new.output->'delegation_plan'->'delegations')
  loop
    if jsonb_typeof(v_item) <> 'object'
       or (v_item - array['agent_id','capability','prompt','title','idempotency_key','max_runtime_seconds']) <> '{}'::jsonb
       or not (v_item ?& array['agent_id','capability','prompt','idempotency_key'])
       or coalesce(v_item->>'agent_id','') !~ '^[a-z][a-z0-9-]{1,62}$'
       or coalesce(v_item->>'capability','') !~ '^[a-z][a-z0-9_.-]{1,95}$'
       or jsonb_typeof(v_item->'prompt') <> 'string'
       or char_length(btrim(v_item->>'prompt')) not between 1 and 20000
       or coalesce(v_item->>'idempotency_key','') !~ '^[A-Za-z0-9_-]{16,128}$'
       or (
         v_item ? 'title' and (
           jsonb_typeof(v_item->'title') <> 'string'
           or char_length(btrim(v_item->>'title')) not between 1 and 120
         )
       )
       or (
         v_item ? 'max_runtime_seconds' and (
           jsonb_typeof(v_item->'max_runtime_seconds') <> 'number'
           or (v_item->>'max_runtime_seconds')::numeric not between 1 and 1800
           or trunc((v_item->>'max_runtime_seconds')::numeric) <> (v_item->>'max_runtime_seconds')::numeric
         )
       ) then
      raise exception 'hermes_delegation_item_invalid' using errcode = '22023';
    end if;
  end loop;

  insert into public.hermes_delegation_outbox (
    task_id,step_id,user_id,parent_run_id,payload
  ) values (
    new.task_id,new.id,new.user_id,v_run_id,new.output->'delegation_plan'
  )
  on conflict (step_id) do nothing;

  if not exists (
    select 1 from public.hermes_delegation_outbox o
     where o.step_id = new.id
       and o.task_id = new.task_id
       and o.user_id = new.user_id
       and o.parent_run_id = v_run_id
       and o.payload = new.output->'delegation_plan'
  ) then
    raise exception 'hermes_delegation_outbox_idempotency_conflict' using errcode = '55000';
  end if;
  return new;
end;
$$;

drop trigger if exists task_steps_enqueue_hermes_delegation on public.task_steps;
create trigger task_steps_enqueue_hermes_delegation
  after update of status on public.task_steps
  for each row execute function public.enqueue_completed_hermes_delegation_plan();

create or replace function public.claim_hermes_delegation_plan(
  p_worker_id text,
  p_lease_seconds integer default 60
)
returns table (
  plan_id uuid, task_id uuid, step_id uuid, user_id uuid,
  parent_run_id uuid, payload jsonb, lease_token uuid
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_id uuid;
  v_token uuid := gen_random_uuid();
begin
  if p_worker_id is null or length(btrim(p_worker_id)) not between 1 and 120
     or p_lease_seconds is null or p_lease_seconds not between 15 and 300 then
    raise exception 'hermes_delegation_claim_invalid' using errcode = '22023';
  end if;

  select o.id into v_id
    from public.hermes_delegation_outbox o
   where o.attempt_count < 8
     and o.available_at <= now()
     and (
       o.status = 'pending'
       or (o.status = 'processing' and o.lease_expires_at < now())
     )
   order by o.created_at
   limit 1
   for update skip locked;
  if not found then return; end if;

  return query
  update public.hermes_delegation_outbox o
     set status = 'processing',
         attempt_count = o.attempt_count + 1,
         lease_owner = btrim(p_worker_id),
         lease_token = v_token,
         lease_expires_at = now() + make_interval(secs => p_lease_seconds),
         updated_at = now()
   where o.id = v_id
  returning o.id,o.task_id,o.step_id,o.user_id,o.parent_run_id,o.payload,o.lease_token;
end;
$$;

create or replace function public.complete_hermes_delegation_plan(
  p_plan_id uuid, p_lease_token uuid, p_result jsonb
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if p_plan_id is null or p_lease_token is null
     or p_result is null or jsonb_typeof(p_result) <> 'object'
     or octet_length(p_result::text) > 16000 then
    raise exception 'hermes_delegation_result_invalid' using errcode = '22023';
  end if;
  update public.hermes_delegation_outbox
     set status = 'submitted', result = p_result, error_code = null,
         lease_owner = null, lease_token = null, lease_expires_at = null, updated_at = now()
   where id = p_plan_id and status = 'processing'
     and lease_token = p_lease_token and lease_expires_at > now();
  return found;
end;
$$;

create or replace function public.fail_hermes_delegation_plan(
  p_plan_id uuid, p_lease_token uuid, p_error_code text
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if p_plan_id is null or p_lease_token is null
     or p_error_code is null or p_error_code !~ '^[a-z0-9_]{1,80}$' then
    raise exception 'hermes_delegation_failure_invalid' using errcode = '22023';
  end if;
  update public.hermes_delegation_outbox
     set status = case when attempt_count >= 8 then 'failed' else 'pending' end,
         available_at = now() + make_interval(secs => least(300,power(2,least(attempt_count,8))::integer)),
         error_code = p_error_code,
         lease_owner = null, lease_token = null, lease_expires_at = null, updated_at = now()
   where id = p_plan_id and status = 'processing'
     and lease_token = p_lease_token and lease_expires_at > now();
  return found;
end;
$$;

revoke all on function public.enqueue_completed_hermes_delegation_plan() from public,anon,authenticated;
revoke all on function public.claim_hermes_delegation_plan(text,integer) from public,anon,authenticated;
revoke all on function public.complete_hermes_delegation_plan(uuid,uuid,jsonb) from public,anon,authenticated;
revoke all on function public.fail_hermes_delegation_plan(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.claim_hermes_delegation_plan(text,integer) to service_role;
grant execute on function public.complete_hermes_delegation_plan(uuid,uuid,jsonb) to service_role;
grant execute on function public.fail_hermes_delegation_plan(uuid,uuid,text) to service_role;

comment on table public.hermes_delegation_outbox is
  'Server-only durable outbox of validated Hermes delegation plans. Delivery retries use handoff idempotency keys.';


create or replace function public.cancel_hermes_delegation_outbox_on_parent_cancel()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.cancel_requested_at is null and new.cancel_requested_at is not null then
    update public.hermes_delegation_outbox
       set status = 'failed',
           error_code = 'parent_task_cancelled',
           lease_owner = null,
           lease_token = null,
           lease_expires_at = null,
           updated_at = now()
     where task_id = new.id
       and user_id = new.user_id
       and status in ('pending','processing');
  end if;
  return new;
end;
$$;

drop trigger if exists tasks_cancel_hermes_delegation_outbox on public.tasks;
create trigger tasks_cancel_hermes_delegation_outbox
  after update of cancel_requested_at on public.tasks
  for each row execute function public.cancel_hermes_delegation_outbox_on_parent_cancel();

revoke all on function public.cancel_hermes_delegation_outbox_on_parent_cancel() from public,anon,authenticated;
grant execute on function public.cancel_hermes_delegation_outbox_on_parent_cancel() to service_role;
