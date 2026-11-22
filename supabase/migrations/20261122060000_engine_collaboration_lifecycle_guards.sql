-- Complete the server-side cancellation and terminal-result edges of
-- approved cross-engine collaboration. Child output remains in task_steps;
-- collaboration events carry identifiers/status only, never raw model output.
create or replace function public.cancel_engine_collaboration_children_on_parent_cancel()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_handoff record;
  v_sequence bigint;
begin
  if old.cancel_requested_at is not null or new.cancel_requested_at is null then
    return new;
  end if;

  -- Lock order is parent -> child task -> handoff. Child terminal handlers use
  -- child -> handoff, so this order avoids a parent-cancel/child-completion
  -- deadlock while still serializing approval and cancellation on the parent.
  update public.tasks child
     set status = 'cancel_requested',
         cancel_requested_at = coalesce(child.cancel_requested_at,now()),
         updated_at = now()
   where child.id in (
     select h.child_task_id
       from public.engine_collaboration_handoffs h
      where h.parent_task_id = new.id
        and h.user_id = new.user_id
        and h.status in ('approved','running')
        and h.child_task_id is not null
   )
     and child.user_id = new.user_id
     and child.status in ('ready','running','cancel_requested')
     and child.cancel_requested_at is null;

  for v_handoff in
    update public.engine_collaboration_handoffs h
       set status = 'cancelled',
           finished_at = now(),
           updated_at = now()
     where h.parent_task_id = new.id
       and h.user_id = new.user_id
       and h.status in ('pending_approval','approved','running')
    returning h.id,h.user_id
  loop
    select coalesce(max(e.sequence),0) + 1
      into v_sequence
      from public.engine_collaboration_events e
     where e.handoff_id = v_handoff.id
       and e.user_id = v_handoff.user_id;

    insert into public.engine_collaboration_events (
      handoff_id,user_id,sequence,event_type,status,metadata
    ) values (
      v_handoff.id,v_handoff.user_id,v_sequence,'handoff.cancelled','cancelled',
      jsonb_build_object('reason','parent_task_cancelled')
    );
  end loop;

  return new;
end;
$$;

drop trigger if exists tasks_cancel_engine_collaboration_children on public.tasks;
create trigger tasks_cancel_engine_collaboration_children
  after update of cancel_requested_at on public.tasks
  for each row
  execute function public.cancel_engine_collaboration_children_on_parent_cancel();

create or replace function public.record_engine_collaboration_child_terminal()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_handoff record;
  v_sequence bigint;
  v_event text;
begin
  if new.status not in ('completed','failed','cancelled')
     or old.status is not distinct from new.status then
    return new;
  end if;

  v_event := case new.status
    when 'completed' then 'handoff.completed'
    when 'failed' then 'handoff.failed'
    else 'handoff.cancelled'
  end;

  for v_handoff in
    update public.engine_collaboration_handoffs h
       set status = new.status, updated_at = now()
     where h.child_task_id = new.id
       and h.user_id = new.user_id
       and h.status in ('approved','running')
    returning h.id, h.user_id
  loop
    select coalesce(max(e.sequence),0) + 1
      into v_sequence
      from public.engine_collaboration_events e
     where e.handoff_id = v_handoff.id
       and e.user_id = v_handoff.user_id;

    -- The complete child result is already durably checkpointed in its
    -- task_steps. Keep this event metadata-only to avoid leaking prompts,
    -- credentials, or arbitrary engine output into the event stream.
    insert into public.engine_collaboration_events (
      handoff_id,user_id,sequence,event_type,status,metadata
    ) values (
      v_handoff.id,v_handoff.user_id,v_sequence,v_event,new.status,
      jsonb_build_object('child_task_id',new.id,'child_status',new.status)
    );
  end loop;

  return new;
end;
$$;

drop trigger if exists tasks_record_engine_collaboration_child_terminal on public.tasks;
create trigger tasks_record_engine_collaboration_child_terminal
  after update of status on public.tasks
  for each row
  execute function public.record_engine_collaboration_child_terminal();

revoke all on function public.cancel_engine_collaboration_children_on_parent_cancel() from public,anon,authenticated;
revoke all on function public.record_engine_collaboration_child_terminal() from public,anon,authenticated;
grant execute on function public.cancel_engine_collaboration_children_on_parent_cancel() to service_role;
grant execute on function public.record_engine_collaboration_child_terminal() to service_role;

comment on function public.cancel_engine_collaboration_children_on_parent_cancel() is
  'Cancels pending handoffs and requests cancellation of approved child tasks when their owner cancels the parent task.';
comment on function public.record_engine_collaboration_child_terminal() is
  'Records metadata-only terminal handoff events when an approved child task completes, fails, or is cancelled.';
