-- Attach conversations to an optional owner-matched project for scoped memory.
-- Existing conversations remain valid and are not reassigned.

alter table public.projects
  add constraint projects_id_user_unique unique (id, user_id);

alter table public.conversations
  add column project_id uuid;

alter table public.conversations
  add constraint conversations_project_owner_fkey
  foreign key (project_id, user_id)
  references public.projects(id, user_id)
  on delete set null (project_id);

create index conversations_owner_project_updated_idx
  on public.conversations (user_id, project_id, updated_at desc)
  where project_id is not null;

comment on column public.conversations.project_id is
  'Optional owner-matched project scope used for project-aware conversation context and memory.';
