-- Bind an optional SULY conversation to a durable task for owner-scoped context continuity.
-- Hermes still receives a fresh task-scoped runtime; SULY remains the session authority.

alter table public.tasks
  add column if not exists conversation_id uuid;

alter table public.tasks
  add constraint tasks_conversation_owner_fkey
  foreign key (conversation_id, user_id)
  references public.conversations(id, user_id)
  on delete set null (conversation_id);

create index if not exists tasks_conversation_created_idx
  on public.tasks(conversation_id, created_at desc)
  where conversation_id is not null;

comment on column public.tasks.conversation_id is
  'Optional owner-matched SULY conversation used to construct bounded task context; never a Hermes runtime/session identifier.';
