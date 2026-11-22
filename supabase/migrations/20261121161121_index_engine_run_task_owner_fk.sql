-- Cover the composite engine_runs(task_id,user_id) ownership foreign key.
create index if not exists engine_runs_task_owner_fk_idx
  on public.engine_runs(task_id,user_id);
