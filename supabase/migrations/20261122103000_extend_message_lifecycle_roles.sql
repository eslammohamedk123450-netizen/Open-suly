-- Extend the persisted message lifecycle without allowing clients to write trusted roles.
-- The authenticated client insert policy remains restricted to role = 'user'.

alter table public.messages
  drop constraint if exists messages_role_check;

alter table public.messages
  add constraint messages_role_check
  check (role in ('user', 'assistant', 'system', 'tool', 'agent', 'error'));

comment on column public.messages.role is
  'Message lifecycle role. Only user messages may be inserted by authenticated clients; trusted roles are server-written.';
