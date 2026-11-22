-- Attach conversations to an optional owner-matched project for scoped memory.
-- Existing conversations remain valid and are not reassigned; safe to re-apply.

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'projects_id_user_unique'
      and conrelid = 'public.projects'::regclass
  ) then
    alter table public.projects
      add constraint projects_id_user_unique unique (id, user_id);
  end if;
end;
$$;

alter table public.conversations
  add column if not exists project_id uuid;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'conversations_project_owner_fkey'
      and conrelid = 'public.conversations'::regclass
  ) then
    alter table public.conversations
      add constraint conversations_project_owner_fkey
      foreign key (project_id, user_id)
      references public.projects(id, user_id)
      on delete set null (project_id);
  end if;
end;
$$;

create index if not exists conversations_owner_project_updated_idx
  on public.conversations (user_id, project_id, updated_at desc)
  where project_id is not null;

comment on column public.conversations.project_id is
  'Optional owner-matched project scope used for project-aware conversation context and memory.';
