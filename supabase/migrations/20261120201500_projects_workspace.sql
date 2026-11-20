-- User-owned project workspaces for grouping SULY tasks.
create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(btrim(name)) between 1 and 120),
  description text not null default '' check (char_length(description) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists projects_owner_updated_idx
  on public.projects (user_id, updated_at desc);

alter table public.projects enable row level security;

drop policy if exists projects_owner_select on public.projects;
create policy projects_owner_select
  on public.projects for select to authenticated
  using (user_id = (select auth.uid()));

revoke all on public.projects from anon, authenticated;
grant select on public.projects to authenticated;
grant all on public.projects to service_role;

alter table public.tasks
  add column if not exists project_id uuid
  references public.projects(id) on delete set null;

create index if not exists tasks_owner_project_created_idx
  on public.tasks (user_id, project_id, created_at desc);

comment on table public.projects is
  'Private user-owned workspaces grouping SULY tasks and future project resources.';
