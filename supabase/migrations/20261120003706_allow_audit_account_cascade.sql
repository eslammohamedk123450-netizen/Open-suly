-- Keep audit events immutable for direct writes while allowing FK cascades on account deletion.
create or replace function public.prevent_tool_approval_event_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if pg_trigger_depth() <= 1 then
    raise exception 'tool_approval_events_are_append_only' using errcode = '55000';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;
revoke all on function public.prevent_tool_approval_event_mutation() from public, anon, authenticated;
