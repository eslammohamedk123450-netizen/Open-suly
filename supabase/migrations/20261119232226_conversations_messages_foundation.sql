-- SULY conversations and messages: user-owned rows with client-safe insert rules.

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null default 'محادثة جديدة'
    check (char_length(btrim(title)) between 1 and 200),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null,
  user_id uuid not null,
  role text not null check (role in ('user', 'assistant', 'system', 'tool')),
  content text not null check (char_length(content) <= 100000),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  constraint messages_conversation_owner_fkey
    foreign key (conversation_id, user_id)
    references public.conversations(id, user_id)
    on delete cascade
);

create index conversations_user_updated_idx
  on public.conversations (user_id, updated_at desc);
create index messages_conversation_created_idx
  on public.messages (conversation_id, created_at asc, id asc);

alter table public.conversations enable row level security;
alter table public.messages enable row level security;

create policy conversations_select_own
  on public.conversations for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy conversations_insert_own
  on public.conversations for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy conversations_update_own
  on public.conversations for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy conversations_delete_own
  on public.conversations for delete
  to authenticated
  using ((select auth.uid()) = user_id);

create policy messages_select_own
  on public.messages for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy messages_insert_user_only
  on public.messages for insert
  to authenticated
  with check (
    (select auth.uid()) = user_id
    and role = 'user'
  );

-- Authenticated clients can create conversations and user messages only.
-- Assistant/system/tool messages are reserved for trusted server-side workers.
grant select, delete on public.conversations to authenticated;
grant insert (user_id, title) on public.conversations to authenticated;
grant update (title) on public.conversations to authenticated;
grant select on public.messages to authenticated;
grant insert (conversation_id, user_id, role, content, metadata) on public.messages to authenticated;
grant all on public.conversations, public.messages to service_role;

create or replace function public.set_conversation_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke all on function public.set_conversation_updated_at() from public, anon, authenticated;

create trigger conversations_set_updated_at
  before update on public.conversations
  for each row execute function public.set_conversation_updated_at();
