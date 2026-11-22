-- Enforce the per-project file limit atomically inside the database.
-- The API previously counted files before inserting, which allowed concurrent
-- requests to exceed the 200-file limit (TOCTOU). This trigger rejects the
-- insert transaction when the project already has 200 files.

create or replace function public.enforce_project_file_limit()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  current_count integer;
  v_project_id uuid;
begin
  -- Serialize inserts for one project so concurrent requests cannot pass
  -- the count check at the same time (TOCTOU protection).
  select p.id into v_project_id
    from public.projects p
   where p.id = new.project_id
     and p.user_id = new.user_id
   for update;
  if not found then
    raise exception 'project_not_found' using errcode = 'P0002';
  end if;

  select count(*)
    into current_count
    from public.project_files
   where project_id = new.project_id
     and user_id = new.user_id;
  if current_count >= 200 then
    raise exception 'project_file_limit_reached'
      using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function public.enforce_project_file_limit() from public, anon, authenticated;

-- Idempotent installation across environments.
drop trigger if exists project_files_enforce_limit
  on public.project_files;
create trigger project_files_enforce_limit
  before insert on public.project_files
  for each row execute function public.enforce_project_file_limit();
