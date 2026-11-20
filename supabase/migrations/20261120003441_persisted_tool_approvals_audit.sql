-- Persisted, owner-scoped tool consent and append-only audit history.
create table if not exists public.tool_approvals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  permission_scope text not null check (char_length(btrim(permission_scope)) between 1 and 160),
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  check (revoked_at is null or revoked_at >= granted_at)
);
create unique index if not exists tool_approvals_one_active_scope
  on public.tool_approvals(user_id, permission_scope) where revoked_at is null;
create index if not exists tool_approvals_owner_history
  on public.tool_approvals(user_id, granted_at desc);

create table if not exists public.tool_approval_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  approval_id uuid references public.tool_approvals(id) on delete set null,
  permission_scope text not null check (char_length(btrim(permission_scope)) between 1 and 160),
  event_type text not null check (event_type in ('granted', 'revoked')),
  actor_user_id uuid not null references auth.users(id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now()
);
create index if not exists tool_approval_events_owner_created
  on public.tool_approval_events(user_id, created_at desc);

alter table public.tool_approvals enable row level security;
alter table public.tool_approval_events enable row level security;
drop policy if exists "Users can read their own tool approvals" on public.tool_approvals;
create policy "Users can read their own tool approvals"
  on public.tool_approvals for select to authenticated
  using ((select auth.uid()) = user_id);
drop policy if exists "Users can read their own tool approval events" on public.tool_approval_events;
create policy "Users can read their own tool approval events"
  on public.tool_approval_events for select to authenticated
  using ((select auth.uid()) = user_id);

revoke all on public.tool_approvals from anon, authenticated;
revoke all on public.tool_approval_events from anon, authenticated;
grant select on public.tool_approvals to authenticated;
grant select on public.tool_approval_events to authenticated;
grant all on public.tool_approvals to service_role;
grant all on public.tool_approval_events to service_role;
grant usage, select on sequence public.tool_approval_events_id_seq to service_role;

create or replace function public.grant_tool_approval(
  p_user_id uuid, p_permission_scope text, p_actor_user_id uuid
) returns uuid language plpgsql security invoker set search_path = ''
as $$
declare v_approval_id uuid;
begin
  if p_user_id is null or p_actor_user_id is null or p_user_id <> p_actor_user_id
     or p_permission_scope is null
     or char_length(btrim(p_permission_scope)) not between 1 and 160 then
    raise exception 'invalid_tool_approval_request' using errcode = '22023';
  end if;
  insert into public.tool_approvals(user_id, permission_scope)
  values (p_user_id, btrim(p_permission_scope))
  on conflict (user_id, permission_scope) where revoked_at is null
  do update set granted_at = public.tool_approvals.granted_at
  returning id into v_approval_id;
  insert into public.tool_approval_events(user_id, approval_id, permission_scope, event_type, actor_user_id)
  values (p_user_id, v_approval_id, btrim(p_permission_scope), 'granted', p_actor_user_id);
  return v_approval_id;
end;
$$;

create or replace function public.revoke_tool_approval(
  p_user_id uuid, p_permission_scope text, p_actor_user_id uuid
) returns integer language plpgsql security invoker set search_path = ''
as $$
declare v_count integer; v_approval_id uuid;
begin
  if p_user_id is null or p_actor_user_id is null or p_user_id <> p_actor_user_id
     or p_permission_scope is null
     or char_length(btrim(p_permission_scope)) not between 1 and 160 then
    raise exception 'invalid_tool_approval_request' using errcode = '22023';
  end if;
  update public.tool_approvals set revoked_at = now()
   where user_id = p_user_id and permission_scope = btrim(p_permission_scope)
     and revoked_at is null
  returning id into v_approval_id;
  get diagnostics v_count = row_count;
  if v_count > 0 then
    insert into public.tool_approval_events(user_id, approval_id, permission_scope, event_type, actor_user_id)
    values (p_user_id, v_approval_id, btrim(p_permission_scope), 'revoked', p_actor_user_id);
  end if;
  return v_count;
end;
$$;
revoke all on function public.grant_tool_approval(uuid, text, uuid) from public, anon, authenticated;
revoke all on function public.revoke_tool_approval(uuid, text, uuid) from public, anon, authenticated;
grant execute on function public.grant_tool_approval(uuid, text, uuid) to service_role;
grant execute on function public.revoke_tool_approval(uuid, text, uuid) to service_role;