-- Distinguish tool authorization events from changes to a user's grant.
alter table public.tool_approval_events
  drop constraint if exists tool_approval_events_event_type_check;
alter table public.tool_approval_events
  add constraint tool_approval_events_event_type_check
  check (event_type in ('granted','revoked','tool_invocation_authorized'));
