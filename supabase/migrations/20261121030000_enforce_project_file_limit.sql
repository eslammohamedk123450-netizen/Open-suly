-- Enforce the 200-file per-project limit atomically at the database level.
-- The API pre-check remains for fast feedback, but this constraint trigger closes
-- the concurrent-request (TOCTOU) gap where parallel inserts exceeded the limit.

create or replace function public.enforce_project_file_limit()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  existing integer;
begin
  select count(*) into existing
    from public.project_files
   where project_files.project_id = new.project_id;
  if existing >= 200 then
    raise exception 'project_file_limit_reached'
      using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function public.enforce_project_file_limit() from public, anon, authenticated;

create constraint trigger enforce_project_file_limit_trigger
  after insert on public.project_files
  deferrable initially deferred
  for each row execute function public.enforce_project_file_limit();

comment on function public.enforce_project_file_limit() is
  'SULY: atomically rejects project file inserts once a project holds 200 files.';
