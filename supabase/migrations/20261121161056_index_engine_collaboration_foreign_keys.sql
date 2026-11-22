-- Cover all remaining engine lifecycle foreign keys for bounded cleanup and joins.
create index if not exists engine_artifacts_task_fk_idx
  on public.engine_artifacts(task_id);
create index if not exists engine_artifacts_run_fk_idx
  on public.engine_artifacts(engine_run_id);
create index if not exists engine_collaboration_artifacts_artifact_owner_fk_idx
  on public.engine_collaboration_artifacts(artifact_id,user_id);
create index if not exists engine_collaboration_artifacts_user_fk_idx
  on public.engine_collaboration_artifacts(user_id);
create index if not exists engine_collaboration_events_user_fk_idx
  on public.engine_collaboration_events(user_id);
create index if not exists engine_collaboration_handoffs_parent_run_fk_idx
  on public.engine_collaboration_handoffs(parent_run_id);
create index if not exists engine_collaboration_handoffs_parent_task_fk_idx
  on public.engine_collaboration_handoffs(parent_task_id);
create index if not exists engine_runs_step_owner_fk_idx
  on public.engine_runs(step_id,user_id);
create index if not exists engine_workspace_locks_run_fk_idx
  on public.engine_workspace_locks(engine_run_id);
create index if not exists engine_workspace_locks_task_fk_idx
  on public.engine_workspace_locks(task_id);
create index if not exists engine_workspace_locks_user_fk_idx
  on public.engine_workspace_locks(user_id);
create index if not exists tasks_conversation_owner_fk_idx
  on public.tasks(conversation_id,user_id) where conversation_id is not null;
