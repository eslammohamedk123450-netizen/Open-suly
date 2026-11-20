-- Durable owner-scoped mapping between SULY projects and upstream OpenCode sessions.
-- Runtime credentials and provider secrets are deliberately never persisted here.
create unique index if not exists projects_id_user_id_uidx
  on public.projects(id, user_id);

create unique index if not exists engine_runs_id_user_id_uidx
  on public.engine_runs(id, user_id);

create table public.opencode_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null,
  task_id uuid,
  engine_run_id uuid,
  upstream_session_id text not null unique
    check (upstream_session_id ~ '^ses[A-Za-z0-9_-]{1,128}$'),
  title text not null check (char_length(btrim(title)) between 1 and 120),
  status text not null default 'active'
    check (status in ('active','paused','completed','failed','expired')),
  workspace_revision text check (workspace_revision is null or char_length(workspace_revision) <= 128),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_activity_at timestamptz not null default now(),
  constraint opencode_sessions_project_owner_fkey
    foreign key (project_id, user_id)
    references public.projects(id, user_id) on delete cascade,
  constraint opencode_sessions_task_owner_fkey
    foreign key (task_id, user_id)
    references public.tasks(id, user_id) on delete cascade,
  constraint opencode_sessions_run_owner_fkey
    foreign key (engine_run_id, user_id)
    references public.engine_runs(id, user_id) on delete cascade,
  check ((task_id is null) = (engine_run_id is null))
);

create index opencode_sessions_project_activity_idx
  on public.opencode_sessions(user_id, project_id, last_activity_at desc);
create index opencode_sessions_task_idx
  on public.opencode_sessions(task_id) where task_id is not null;

alter table public.opencode_sessions enable row level security;
create policy opencode_sessions_select_own
  on public.opencode_sessions for select to authenticated
  using ((select auth.uid()) = user_id);

revoke all on public.opencode_sessions from anon, authenticated;
grant select on public.opencode_sessions to authenticated;
grant all on public.opencode_sessions to service_role;

create or replace function public.set_opencode_session_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  new.last_activity_at = greatest(new.last_activity_at, old.last_activity_at);
  return new;
end;
$$;

revoke all on function public.set_opencode_session_updated_at() from public, anon, authenticated;
create trigger opencode_sessions_set_updated_at
  before update on public.opencode_sessions
  for each row execute function public.set_opencode_session_updated_at();

comment on table public.opencode_sessions is
  'Owner-scoped durable mapping for OpenCode upstream sessions. No runtime credentials, prompts, or model output are stored.';
