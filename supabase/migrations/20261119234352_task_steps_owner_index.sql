-- Cover the composite ownership foreign key used by task_steps.
create index task_steps_task_owner_idx on public.task_steps (task_id, user_id);
