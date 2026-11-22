-- SULY-owned project workspace and OpenCode lifecycle persistence.
-- Runtime services use a server-side Supabase client; browser access is owner-scoped.
create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 120),
  description text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint projects_id_user_unique unique (id, user_id)
);
-- The projects table may have been created by the earlier workspace migration,
-- whose original definition had only the id primary key. Ensure the composite
-- owner key exists before creating any composite tenant foreign keys.
do $
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'projects_id_user_unique'
      and conrelid = 'public.projects'::regclass
  ) then
    alter table public.projects
      add constraint projects_id_user_unique unique (id, user_id);
  end if;
end;
$;

create index if not exists projects_owner_updated_idx on public.projects(user_id, updated_at desc);

create table if not exists public.project_files (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  path text not null check (length(path) between 1 and 240),
  content text not null,
  size_bytes integer not null check (size_bytes between 0 and 262144),
  updated_at timestamptz not null default now(),
  constraint project_files_project_owner_fk foreign key(project_id,user_id)
    references public.projects(id,user_id) on delete cascade,
  constraint project_files_project_path_unique unique(project_id,path),
  constraint project_files_content_size_check check (octet_length(content)=size_bytes)
);
create index if not exists project_files_owner_project_idx on public.project_files(user_id,project_id,path);

create table if not exists public.opencode_task_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null,
  task_id uuid not null references public.tasks(id) on delete cascade,
  engine_run_id uuid not null,
  runtime_id uuid,
  upstream_session_id text,
  workspace_revision text not null check (workspace_revision ~ '^[0-9a-f]{64}$'),
  status text not null default 'queued' check (status in ('queued','provisioning','running','waiting_approval','collecting','review_ready','applying','completed','failed','cancelled','expired')),
  error_code text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(engine_run_id),
  foreign key(project_id,user_id) references public.projects(id,user_id) on delete cascade
);
create index if not exists opencode_runs_owner_project_idx on public.opencode_task_runs(user_id,project_id,created_at desc);
create index if not exists opencode_runs_recovery_idx on public.opencode_task_runs(status,updated_at) where status in ('provisioning','running','waiting_approval','collecting','applying');

create table if not exists public.opencode_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null,
  task_id uuid references public.tasks(id) on delete set null,
  engine_run_id uuid,
  upstream_session_id text not null check (upstream_session_id ~ '^ses[A-Za-z0-9_-]{1,128}$'),
  title text not null check (length(btrim(title)) between 1 and 120),
  status text not null default 'active' check (status in ('active','paused','completed','failed','expired')),
  workspace_revision text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_activity_at timestamptz not null default now(),
  foreign key(project_id,user_id) references public.projects(id,user_id) on delete cascade,
  unique(user_id,upstream_session_id)
);
create index if not exists opencode_sessions_project_activity_idx on public.opencode_sessions(user_id,project_id,last_activity_at desc);

create table if not exists public.opencode_task_events (
  id bigint generated always as identity primary key,
  run_id uuid not null references public.opencode_task_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  sequence integer not null check (sequence > 0),
  event_type text not null check (event_type in ('task.started','task.status','task.completed','task.failed','task.cancelled','permission.requested','permission.decided','changes.collected','changes.approved','changes.rejected')),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(run_id,sequence)
);
create index if not exists opencode_events_owner_run_idx on public.opencode_task_events(user_id,run_id,sequence);

create table if not exists public.opencode_approvals (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.opencode_task_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id text not null check (session_id ~ '^ses[A-Za-z0-9_-]{1,128}$'),
  upstream_permission_id text not null,
  permission_type text not null,
  resource jsonb not null default '{}'::jsonb,
  status text not null default 'pending' check (status in ('pending','processing','approved_once','rejected','expired')),
  created_at timestamptz not null default now(),
  decided_at timestamptz,
  unique(run_id,upstream_permission_id)
);
create index if not exists opencode_approvals_pending_idx on public.opencode_approvals(user_id,run_id,created_at) where status='pending';

create table if not exists public.opencode_change_sets (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.opencode_task_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null,
  base_revision text not null check (base_revision ~ '^[0-9a-f]{64}$'),
  changes jsonb not null check (jsonb_typeof(changes)='array'),
  status text not null default 'review_ready' check (status in ('review_ready','applying','applied','stale','rejected','failed')),
  created_at timestamptz not null default now(),
  decided_at timestamptz,
  foreign key(project_id,user_id) references public.projects(id,user_id) on delete cascade
);
create index if not exists opencode_changesets_owner_project_idx on public.opencode_change_sets(user_id,project_id,created_at desc);

-- All engine state is server-written; authenticated users may read only their own rows.
do $$
declare t text;
begin
  foreach t in array array['projects','project_files','opencode_task_runs','opencode_sessions','opencode_task_events','opencode_approvals','opencode_change_sets']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from public, anon, authenticated', t);
    execute format('grant all on table public.%I to service_role', t);
    execute format('grant select on table public.%I to authenticated', t);
    execute format('drop policy if exists %I on public.%I', t || '_owner_select', t);
    execute format('create policy %I on public.%I for select to authenticated using ((select auth.uid()) = user_id)', t || '_owner_select', t);
  end loop;
end $$;

-- Atomic compare-and-swap application of a reviewed OpenCode changeset.
create or replace function public.apply_opencode_change_set(p_user_id uuid, p_change_set_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  cs public.opencode_change_sets%rowtype;
  actual_revision text;
  revision_payload bytea;
  item jsonb;
  file_path text;
  action_name text;
  file_content text;
  expected_sha text;
begin
  select * into cs from public.opencode_change_sets
   where id=p_change_set_id and user_id=p_user_id and status='review_ready'
   for update;
  if not found then return jsonb_build_object('applied',false,'reason','not_reviewable'); end if;

  select coalesce(string_agg(
      convert_to(pf.path,'UTF8') || decode('00','hex') ||
      convert_to(encode(digest(convert_to(pf.content,'UTF8'),'sha256'),'hex'),'UTF8') ||
      decode('0a','hex'), ''::bytea order by pf.path
    ), ''::bytea)
    into revision_payload
    from public.project_files pf
   where pf.project_id=cs.project_id and pf.user_id=p_user_id;
  actual_revision := encode(digest(coalesce(revision_payload,''::bytea),'sha256'),'hex');
  if actual_revision <> cs.base_revision then
    update public.opencode_change_sets set status='stale' where id=cs.id;
    return jsonb_build_object('applied',false,'reason','stale_revision','current_revision',actual_revision);
  end if;

  update public.opencode_change_sets set status='applying' where id=cs.id and status='review_ready';
  if not found then return jsonb_build_object('applied',false,'reason','claim_conflict'); end if;

  for item in select value from jsonb_array_elements(cs.changes)
  loop
    file_path := item->>'path';
    action_name := item->>'action';
    if file_path is null or file_path='' or file_path like '/%' or file_path ~ '(^|/)\.\.(/|$)' or file_path like '%\\%' then
      raise exception 'invalid_change_path';
    end if;
    if action_name in ('create','update') then
      file_content := item->>'content';
      expected_sha := encode(digest(convert_to(file_content,'UTF8'),'sha256'),'hex');
      if expected_sha <> item->>'sha256' then raise exception 'change_digest_mismatch'; end if;
      insert into public.project_files(project_id,user_id,path,content,size_bytes,updated_at)
      values(cs.project_id,p_user_id,file_path,file_content,octet_length(file_content),now())
      on conflict(project_id,path) do update set
        content=excluded.content,size_bytes=excluded.size_bytes,updated_at=now()
      where public.project_files.user_id=p_user_id;
    elsif action_name='delete' then
      delete from public.project_files where project_id=cs.project_id and user_id=p_user_id and path=file_path;
    else
      raise exception 'invalid_change_action';
    end if;
  end loop;

  update public.opencode_change_sets set status='applied',decided_at=now() where id=cs.id;
  update public.opencode_task_runs set status='completed',finished_at=now(),updated_at=now()
   where id=cs.run_id and user_id=p_user_id and status in ('review_ready','applying');
  return jsonb_build_object('applied',true,'change_set_id',cs.id);
exception when others then
  update public.opencode_change_sets set status='failed' where id=p_change_set_id and user_id=p_user_id;
  raise;
end;
$$;
revoke all on function public.apply_opencode_change_set(uuid,uuid) from public, anon, authenticated;
grant execute on function public.apply_opencode_change_set(uuid,uuid) to service_role;

-- Correct the skill owner policy plan and index its approved_by foreign key.
drop policy if exists hermes_skill_owner_select on public.hermes_skill_approvals;
create policy hermes_skill_owner_select on public.hermes_skill_approvals
  for select to authenticated using ((select auth.uid()) = user_id);
create index if not exists hermes_skill_approved_by_idx on public.hermes_skill_approvals(approved_by);
