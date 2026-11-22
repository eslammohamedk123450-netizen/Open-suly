-- Durable Hermes session and memory records remain owned by SULY.
create table if not exists public.hermes_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid,
  conversation_id uuid references public.conversations(id) on delete set null,
  task_id uuid references public.tasks(id) on delete set null,
  engine_session_id text not null,
  status text not null default 'active' check (status in ('active','paused','completed','failed','expired')),
  context_revision integer not null default 1 check (context_revision > 0),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_activity_at timestamptz not null default now(),
  foreign key(project_id,user_id) references public.projects(id,user_id) on delete cascade,
  unique(user_id,engine_session_id)
);
create index if not exists hermes_sessions_owner_activity_idx
  on public.hermes_sessions(user_id,last_activity_at desc);
create index if not exists hermes_sessions_project_idx
  on public.hermes_sessions(user_id,project_id,last_activity_at desc)
  where project_id is not null;

create table if not exists public.hermes_memory_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  scope text not null check (scope in ('user','project','conversation')),
  project_id uuid,
  conversation_id uuid references public.conversations(id) on delete cascade,
  memory_key text not null check (length(memory_key) between 1 and 160),
  content jsonb not null check (jsonb_typeof(content) in ('object','array','string','number','boolean')),
  source text not null default 'suly' check (source in ('suly','user_approved_import','agent_proposal')),
  status text not null default 'active' check (status in ('active','archived')),
  revision integer not null default 1 check (revision > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key(project_id,user_id) references public.projects(id,user_id) on delete cascade,
  constraint hermes_memory_scope_target_check check (
    (scope='user' and project_id is null and conversation_id is null)
    or (scope='project' and project_id is not null and conversation_id is null)
    or (scope='conversation' and conversation_id is not null)
  ),
  unique nulls not distinct(user_id,scope,memory_key,project_id,conversation_id)
);
create index if not exists hermes_memory_owner_scope_idx
  on public.hermes_memory_entries(user_id,scope,updated_at desc);
create index if not exists hermes_memory_project_idx
  on public.hermes_memory_entries(user_id,project_id,updated_at desc)
  where project_id is not null;

alter table public.hermes_sessions enable row level security;
alter table public.hermes_memory_entries enable row level security;
revoke all on table public.hermes_sessions, public.hermes_memory_entries from public, anon, authenticated;
grant all on table public.hermes_sessions, public.hermes_memory_entries to service_role;
grant select on table public.hermes_sessions, public.hermes_memory_entries to authenticated;
drop policy if exists hermes_sessions_owner_select on public.hermes_sessions;
create policy hermes_sessions_owner_select on public.hermes_sessions
  for select to authenticated using ((select auth.uid())=user_id);
drop policy if exists hermes_memory_owner_select on public.hermes_memory_entries;
create policy hermes_memory_owner_select on public.hermes_memory_entries
  for select to authenticated using ((select auth.uid())=user_id);
comment on table public.hermes_sessions is 'SULY-owned mapping of Hermes upstream sessions to user, project, conversation and task context.';
comment on table public.hermes_memory_entries is 'SULY-owned memory source of truth; Hermes receives only explicitly scoped, approved context.';
