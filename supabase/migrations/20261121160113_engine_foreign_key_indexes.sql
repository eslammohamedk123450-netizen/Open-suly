-- Cover foreign-key lookups used by owner-scoped engine lifecycle cleanup.
create index if not exists hermes_memory_conversation_fk_idx on public.hermes_memory_entries(conversation_id);
create index if not exists hermes_memory_project_owner_fk_idx on public.hermes_memory_entries(project_id,user_id);
create index if not exists hermes_sessions_conversation_fk_idx on public.hermes_sessions(conversation_id);
create index if not exists hermes_sessions_project_owner_fk_idx on public.hermes_sessions(project_id,user_id);
create index if not exists hermes_sessions_task_fk_idx on public.hermes_sessions(task_id);
create index if not exists opencode_changesets_project_owner_fk_idx on public.opencode_change_sets(project_id,user_id);
create index if not exists opencode_changesets_run_fk_idx on public.opencode_change_sets(run_id);
create index if not exists opencode_sessions_project_owner_fk_idx on public.opencode_sessions(project_id,user_id);
create index if not exists opencode_sessions_task_fk_idx on public.opencode_sessions(task_id);
create index if not exists opencode_runs_project_owner_fk_idx on public.opencode_task_runs(project_id,user_id);
create index if not exists opencode_runs_task_fk_idx on public.opencode_task_runs(task_id);
create index if not exists project_files_project_owner_fk_idx on public.project_files(project_id,user_id);
