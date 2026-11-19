-- Keep worker lease internals private while exposing task progress to owners.
revoke select on public.tasks from authenticated;
grant select (
  id, user_id, title, request, status, plan, result, error_code, error_message,
  attempt_count, max_attempts, cancel_requested_at, started_at, completed_at,
  created_at, updated_at
) on public.tasks to authenticated;

revoke select on public.task_steps from authenticated;
grant select (
  id, task_id, user_id, step_key, title, description, step_order, depends_on,
  status, input, output, error_code, error_message, attempt_count, max_attempts,
  started_at, completed_at, created_at, updated_at
) on public.task_steps to authenticated;
