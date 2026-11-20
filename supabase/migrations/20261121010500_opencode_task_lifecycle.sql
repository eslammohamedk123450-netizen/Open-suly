-- Durable, owner-scoped OpenCode task lifecycle, approvals, events and reviewable changes.
-- Server-side workers use the service role; authenticated clients receive read-only access.
begin;

create table if not exists public.opencode_task_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  task_id uuid not null,
  engine_run_id uuid not null,
  runtime_id text,
  upstream_session_id text,
  status text not null default 'queued'
    check (status in ('queued','provisioning','running','waiting_approval','collecting','review_ready','applying','completed','failed','cancelled','expired')),
  workspace_revision text not null check (workspace_revision ~ '^[0-9a-f]{64}$'),
  error_code text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (task_id, engine_run_id),
  unique (runtime_id)
);

create table if not exists public.opencode_task_events (
  id bigint generated always as identity primary key,
  run_id uuid not null references public.opencode_task_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  sequence bigint not null check (sequence > 0),
  event_type text not null check (length(event_type) between 1 and 80),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (run_id, sequence),
  check (octet_length(payload::text) <= 16384)
);

create table if not exists public.opencode_approvals (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.opencode_task_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  upstream_permission_id text not null check (length(upstream_permission_id) between 1 and 160),
  session_id text not null check (session_id ~ '^ses[A-Za-z0-9_-]{1,128}$'),
  permission_type text not null check (length(permission_type) between 1 and 80),
  resource jsonb not null default '{}'::jsonb,
  status text not null default 'pending' check (status in ('pending','processing','approved_once','approved_always','rejected','expired')),
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  unique (run_id, upstream_permission_id)
);

create table if not exists public.opencode_change_sets (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.opencode_task_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  base_revision text not null check (base_revision ~ '^[0-9a-f]{64}$'),
  status text not null default 'review_ready' check (status in ('review_ready','applying','approved','applied','stale','rejected')),
  changes jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  decided_at timestamptz,
  check (octet_length(changes::text) <= 2097152)
);

create index if not exists opencode_task_runs_owner_project_idx
  on public.opencode_task_runs(user_id, project_id, created_at desc);
create index if not exists opencode_task_events_owner_run_idx
  on public.opencode_task_events(user_id, run_id, sequence);
create index if not exists opencode_approvals_pending_idx
  on public.opencode_approvals(user_id, status, created_at desc);
create index if not exists opencode_change_sets_owner_project_idx
  on public.opencode_change_sets(user_id, project_id, created_at desc);

alter table public.opencode_task_runs enable row level security;
alter table public.opencode_task_events enable row level security;
alter table public.opencode_approvals enable row level security;
alter table public.opencode_change_sets enable row level security;

drop policy if exists "users read own opencode task runs" on public.opencode_task_runs;
create policy "users read own opencode task runs" on public.opencode_task_runs
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "users read own opencode task events" on public.opencode_task_events;
create policy "users read own opencode task events" on public.opencode_task_events
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "users read own opencode approvals" on public.opencode_approvals;
create policy "users read own opencode approvals" on public.opencode_approvals
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "users read own opencode change sets" on public.opencode_change_sets;
create policy "users read own opencode change sets" on public.opencode_change_sets
  for select to authenticated using ((select auth.uid()) = user_id);

revoke all on public.opencode_task_runs, public.opencode_task_events,
  public.opencode_approvals, public.opencode_change_sets from anon, authenticated;
grant select on public.opencode_task_runs, public.opencode_task_events,
  public.opencode_approvals, public.opencode_change_sets to authenticated;
grant all on public.opencode_task_runs, public.opencode_task_events,
  public.opencode_approvals, public.opencode_change_sets to service_role;
grant usage, select on sequence public.opencode_task_events_id_seq to service_role;

commit;
