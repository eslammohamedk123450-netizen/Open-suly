-- Enforce tenant ownership at every engine-to-project/conversation/task edge.
-- Existing rows are preserved; constraints fail closed if cross-owner links exist.
alter table public.tasks drop constraint if exists tasks_project_id_fkey;
alter table public.tasks
  add constraint tasks_project_owner_fkey
  foreign key (project_id, user_id)
  references public.projects(id, user_id)
  on delete set null (project_id);

alter table public.hermes_sessions
  drop constraint if exists hermes_sessions_conversation_id_fkey,
  drop constraint if exists hermes_sessions_task_id_fkey;
alter table public.hermes_sessions
  add constraint hermes_sessions_conversation_owner_fkey
    foreign key (conversation_id, user_id)
    references public.conversations(id, user_id)
    on delete set null (conversation_id),
  add constraint hermes_sessions_task_owner_fkey
    foreign key (task_id, user_id)
    references public.tasks(id, user_id)
    on delete set null (task_id);

alter table public.hermes_memory_entries
  drop constraint if exists hermes_memory_entries_conversation_id_fkey;
alter table public.hermes_memory_entries
  add constraint hermes_memory_conversation_owner_fkey
  foreign key (conversation_id, user_id)
  references public.conversations(id, user_id)
  on delete cascade;

alter table public.opencode_sessions
  drop constraint if exists opencode_sessions_task_id_fkey;
alter table public.opencode_sessions
  add constraint opencode_sessions_task_owner_fkey
  foreign key (task_id, user_id)
  references public.tasks(id, user_id)
  on delete set null (task_id);

alter table public.opencode_task_runs
  drop constraint if exists opencode_task_runs_task_id_fkey;
alter table public.opencode_task_runs
  add constraint opencode_task_runs_task_owner_fkey
  foreign key (task_id, user_id)
  references public.tasks(id, user_id)
  on delete cascade;

create index if not exists tasks_project_owner_fk_idx
  on public.tasks(project_id, user_id) where project_id is not null;
create index if not exists hermes_sessions_conversation_owner_fk_idx
  on public.hermes_sessions(conversation_id, user_id) where conversation_id is not null;
create index if not exists hermes_sessions_task_owner_fk_idx
  on public.hermes_sessions(task_id, user_id) where task_id is not null;
create index if not exists hermes_memory_conversation_owner_fk_idx
  on public.hermes_memory_entries(conversation_id, user_id) where conversation_id is not null;
create index if not exists opencode_sessions_task_owner_fk_idx
  on public.opencode_sessions(task_id, user_id) where task_id is not null;
create index if not exists opencode_task_runs_task_owner_fk_idx
  on public.opencode_task_runs(task_id, user_id);
