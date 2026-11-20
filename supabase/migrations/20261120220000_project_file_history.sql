-- Immutable snapshots of previous project-file contents for safe recovery.
create table if not exists public.project_file_revisions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  file_id uuid not null references public.project_files(id) on delete cascade,
  path text not null check (char_length(path) between 1 and 512),
  content text not null check (octet_length(content) <= 262144),
  size_bytes integer not null check (size_bytes between 0 and 262144),
  created_at timestamptz not null default now()
);

create index if not exists project_file_revisions_owner_file_created_idx
  on public.project_file_revisions (user_id, file_id, created_at desc);

alter table public.project_file_revisions enable row level security;
revoke all on public.project_file_revisions from anon, authenticated;
grant all on public.project_file_revisions to service_role;

create or replace function public.capture_project_file_revision()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if old.content is distinct from new.content then
    insert into public.project_file_revisions
      (project_id, user_id, file_id, path, content, size_bytes)
    values
      (old.project_id, old.user_id, old.id, old.path, old.content, old.size_bytes);
  end if;
  return new;
end;
$$;

drop trigger if exists project_file_revision_before_update on public.project_files;
create trigger project_file_revision_before_update
before update on public.project_files
for each row execute function public.capture_project_file_revision();

comment on table public.project_file_revisions is
  'Immutable previous versions of owner-scoped text project files, captured before content changes.';
