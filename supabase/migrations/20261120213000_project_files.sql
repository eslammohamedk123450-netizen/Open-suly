-- Text-based project files for the SULY workspace editor.
create table if not exists public.project_files (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  path text not null check (char_length(path) between 1 and 512),
  content text not null default '' check (octet_length(content) <= 262144),
  size_bytes integer not null default 0 check (size_bytes between 0 and 262144),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, path)
);

create index if not exists project_files_owner_project_path_idx
  on public.project_files (user_id, project_id, path);

alter table public.project_files enable row level security;
revoke all on public.project_files from anon, authenticated;
grant all on public.project_files to service_role;

comment on table public.project_files is
  'Owner-scoped UTF-8 text source files for SULY project workspaces; binary uploads are not supported.';
