-- User-owned SULY agent memory.
-- Only explicit user-authored/approved notes are stored; engines never write memory directly.

create table if not exists public.agent_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  memory_key text not null,
  content text not null,
  tags text[] not null default '{}'::text[],
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_memories_key_check
    check (memory_key ~ '^[a-z0-9][a-z0-9_-]{1,63}$'),
  constraint agent_memories_content_check
    check (char_length(btrim(content)) between 1 and 2000),
  constraint agent_memories_tags_count_check
    check (coalesce(array_length(tags, 1), 0) <= 8),
  constraint agent_memories_status_check
    check (status in ('active','archived')),
  constraint agent_memories_user_key_unique
    unique (user_id, memory_key)
);

create index if not exists agent_memories_owner_active_updated_idx
  on public.agent_memories(user_id, updated_at desc)
  where status = 'active';

alter table public.agent_memories enable row level security;

revoke all on table public.agent_memories from public, anon, authenticated;
grant select on table public.agent_memories to authenticated;
grant all on table public.agent_memories to service_role;

drop policy if exists agent_memories_owner_select on public.agent_memories;
create policy agent_memories_owner_select
  on public.agent_memories
  for select
  to authenticated
  using (auth.uid() = user_id);

comment on table public.agent_memories is
  'Explicit user-authored or user-approved memory notes. Engines receive bounded read-only context; memory writes are user-mediated.';
comment on column public.agent_memories.content is
  'Bounded non-secret memory note. Never store passwords, API keys, access tokens, private keys, or sensitive personal data.';
