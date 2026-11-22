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

