-- Durable, owner-scoped collaboration records and immutable artifact references.
-- Engine processes exchange references only; artifact bytes remain in SULY-controlled storage.
create table if not exists public.engine_artifacts (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks(id) on delete cascade,
  engine_run_id uuid not null references public.engine_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid,
  storage_bucket text not null,
  storage_object_path text not null,
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  byte_size bigint not null check (byte_size between 0 and 5242880),
  media_type text not null check (media_type ~ '^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$'),
  created_at timestamptz not null default now(),
  unique (storage_bucket, storage_object_path),
  unique (id, user_id)
);

create index if not exists engine_artifacts_owner_task_idx
  on public.engine_artifacts(user_id, task_id, created_at desc);

alter table public.engine_artifacts enable row level security;
revoke all on public.engine_artifacts from anon, authenticated;
grant select on public.engine_artifacts to authenticated;
grant all on public.engine_artifacts to service_role;
create policy engine_artifacts_owner_select on public.engine_artifacts
  for select to authenticated using (user_id = (select auth.uid()));

create table if not exists public.engine_collaboration_handoffs (
  id uuid primary key default gen_random_uuid(),
  parent_task_id uuid not null references public.tasks(id) on delete cascade,
  child_task_id uuid references public.tasks(id) on delete set null,
  parent_run_id uuid not null references public.engine_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  source_engine text not null check (source_engine ~ '^[a-z][a-z0-9-]{1,62}$'),
  target_engine text not null check (target_engine ~ '^[a-z][a-z0-9-]{1,62}$'),
  capability text not null check (capability ~ '^[a-z][a-z0-9_.-]{1,95}$'),
  status text not null default 'pending_approval'
    check (status in ('pending_approval','approved','running','completed','failed','cancelled','rejected')),
  depth smallint not null default 1 check (depth between 1 and 3),
  max_child_tasks smallint not null default 1 check (max_child_tasks between 1 and 8),
  max_parallel_children smallint not null default 1 check (max_parallel_children between 1 and 2),
  max_runtime_seconds integer not null default 300 check (max_runtime_seconds between 1 and 1800),
  max_input_bytes integer not null default 64000 check (max_input_bytes between 1 and 64000),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  approved_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  error_code text check (error_code is null or error_code ~ '^[a-z0-9_]{1,96}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (source_engine <> target_engine),
  check (max_parallel_children <= max_child_tasks),
  unique (user_id, idempotency_key)
);

create index if not exists engine_collaboration_owner_parent_idx
  on public.engine_collaboration_handoffs(user_id, parent_task_id, created_at desc);
create index if not exists engine_collaboration_status_idx
  on public.engine_collaboration_handoffs(status, updated_at);

alter table public.engine_collaboration_handoffs enable row level security;
revoke all on public.engine_collaboration_handoffs from anon, authenticated;
grant select on public.engine_collaboration_handoffs to authenticated;
grant all on public.engine_collaboration_handoffs to service_role;
create policy engine_collaboration_owner_select on public.engine_collaboration_handoffs
  for select to authenticated using (user_id = (select auth.uid()));

create table if not exists public.engine_collaboration_artifacts (
  handoff_id uuid not null references public.engine_collaboration_handoffs(id) on delete cascade,
  artifact_id uuid not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  direction text not null check (direction in ('input','output')),
  created_at timestamptz not null default now(),
  primary key (handoff_id, artifact_id, direction),
  foreign key (artifact_id, user_id)
    references public.engine_artifacts(id, user_id) on delete cascade
);

alter table public.engine_collaboration_artifacts enable row level security;
revoke all on public.engine_collaboration_artifacts from anon, authenticated;
grant select on public.engine_collaboration_artifacts to authenticated;
grant all on public.engine_collaboration_artifacts to service_role;
create policy engine_collaboration_artifacts_owner_select on public.engine_collaboration_artifacts
  for select to authenticated using (user_id = (select auth.uid()));

create table if not exists public.engine_collaboration_events (
  id uuid primary key default gen_random_uuid(),
  handoff_id uuid not null references public.engine_collaboration_handoffs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  sequence bigint not null check (sequence between 0 and 1000000000),
  event_type text not null check (event_type in (
    'handoff.created','handoff.approved','handoff.started','handoff.completed',
    'handoff.failed','handoff.cancelled','artifact.published',
    'review.requested','review.accepted','review.rejected',
    'workspace.locked','workspace.released'
  )),
  status text check (status is null or status in ('pending','approved','running','completed','failed','cancelled')),
  metadata jsonb not null default '{}'::jsonb
    check (jsonb_typeof(metadata) = 'object' and octet_length(metadata::text) <= 2048),
  created_at timestamptz not null default now(),
  unique (handoff_id, sequence)
);

alter table public.engine_collaboration_events enable row level security;
revoke all on public.engine_collaboration_events from anon, authenticated;
grant select on public.engine_collaboration_events to authenticated;
grant all on public.engine_collaboration_events to service_role;
create policy engine_collaboration_events_owner_select on public.engine_collaboration_events
  for select to authenticated using (user_id = (select auth.uid()));

-- One writer per project at a time. The lock is task/run scoped and expires.
create table if not exists public.engine_workspace_locks (
  project_id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  engine_id text not null check (engine_id ~ '^[a-z][a-z0-9-]{1,62}$'),
  task_id uuid not null references public.tasks(id) on delete cascade,
  engine_run_id uuid not null references public.engine_runs(id) on delete cascade,
  lease_token_hash text not null check (lease_token_hash ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists engine_workspace_locks_expiry_idx
  on public.engine_workspace_locks(expires_at);

alter table public.engine_workspace_locks enable row level security;
revoke all on public.engine_workspace_locks from anon, authenticated;
grant select on public.engine_workspace_locks to authenticated;
grant all on public.engine_workspace_locks to service_role;
create policy engine_workspace_locks_owner_select on public.engine_workspace_locks
  for select to authenticated using (user_id = (select auth.uid()));

comment on table public.engine_artifacts is
  'Immutable owner-scoped artifact metadata; engines receive opaque references, never shared storage credentials.';
comment on table public.engine_collaboration_handoffs is
  'SULY-owned bounded cross-engine delegation contract. Engine-to-engine handoffs require a SULY approval.';
comment on table public.engine_collaboration_events is
  'Metadata-only collaboration events; never store prompts, tool arguments, raw outputs, or credentials.';
comment on table public.engine_workspace_locks is
  'Prevents concurrent engine writers from mutating the same project workspace.';
