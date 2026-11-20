-- Preserve audit rows independently of Auth user deletion and make events immutable.
alter table public.tool_approval_events
  drop constraint if exists tool_approval_events_actor_user_id_fkey;

create or replace function public.prevent_tool_approval_event_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception 'tool_approval_events_are_append_only' using errcode = '55000';
end;
$$;
revoke all on function public.prevent_tool_approval_event_mutation() from public, anon, authenticated;
drop trigger if exists tool_approval_events_immutable on public.tool_approval_events;
create trigger tool_approval_events_immutable
before update or delete on public.tool_approval_events
for each row execute function public.prevent_tool_approval_event_mutation();
