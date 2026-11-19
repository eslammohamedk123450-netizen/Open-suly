-- SULY durable task and DAG execution foundation.
create table public.tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(btrim(title)) between 1 and 200),
  request text not null check (char_length(btrim(request)) between 1 and 20000),
  status text not null default 'queued'
    check (status in ('queued','planning','ready','running','waiting_approval','completed','failed','cancel_requested','cancelled')),
  plan jsonb not null default '[]'::jsonb check (jsonb_typeof(plan) = 'array'),
  result jsonb not null default '{}'::jsonb check (jsonb_typeof(result) = 'object'),
  error_code text,
  error_message text,
  idempotency_key text not null check (char_length(idempotency_key) between 8 and 128),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 3 check (max_attempts between 1 and 10),
  cancel_requested_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, idempotency_key),
  unique (id, user_id)
);

create table public.task_steps (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null,
  user_id uuid not null,
  step_key text not null check (char_length(step_key) between 1 and 100),
  title text not null check (char_length(btrim(title)) between 1 and 200),
  description text not null default '' check (char_length(description) <= 4000),
  step_order integer not null check (step_order >= 0),
  depends_on jsonb not null default '[]'::jsonb check (jsonb_typeof(depends_on) = 'array'),
  status text not null default 'pending'
    check (status in ('pending','ready','running','completed','failed','blocked','cancelled')),
  input jsonb not null default '{}'::jsonb check (jsonb_typeof(input) = 'object'),
  output jsonb not null default '{}'::jsonb check (jsonb_typeof(output) = 'object'),
  error_code text,
  error_message text,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 3 check (max_attempts between 1 and 10),
  lease_owner text,
  lease_token uuid,
  lease_expires_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint task_steps_task_owner_fkey
    foreign key (task_id, user_id) references public.tasks(id, user_id) on delete cascade,
  unique (task_id, step_key),
  unique (task_id, step_order),
  check ((lease_token is null) = (lease_expires_at is null))
);

create index tasks_user_created_idx on public.tasks(user_id, created_at desc);
create index tasks_worker_queue_idx on public.tasks(status, created_at) where status in ('queued','ready','cancel_requested');
create index task_steps_ready_idx on public.task_steps(status, task_id, step_order) where status in ('pending','ready','running');
create index task_steps_expired_lease_idx on public.task_steps(lease_expires_at) where lease_token is not null;

alter table public.tasks enable row level security;
alter table public.task_steps enable row level security;

create policy tasks_select_own on public.tasks for select to authenticated
  using ((select auth.uid()) = user_id);
create policy task_steps_select_own on public.task_steps for select to authenticated
  using ((select auth.uid()) = user_id);

grant select on public.tasks, public.task_steps to authenticated;
grant all on public.tasks, public.task_steps to service_role;

create or replace function public.set_task_updated_at()
returns trigger language plpgsql set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
revoke all on function public.set_task_updated_at() from public, anon, authenticated;

create trigger tasks_set_updated_at before update on public.tasks
  for each row execute function public.set_task_updated_at();
create trigger task_steps_set_updated_at before update on public.task_steps
  for each row execute function public.set_task_updated_at();

comment on table public.tasks is 'Durable user-owned task requests and execution state. Mutations are server-only.';
comment on table public.task_steps is 'DAG execution steps, checkpoints, retries, and worker lease state. Mutations are server-only.';
