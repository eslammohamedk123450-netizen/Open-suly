-- Force authenticated clients to use the default user role and keep timestamps server-managed.
alter table public.messages alter column role set default 'user';
revoke insert (role) on public.messages from authenticated;
revoke update (updated_at) on public.conversations from authenticated;

create or replace function public.bump_conversation_updated_at_from_message()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- Updating the title to itself invokes the timestamp trigger without
  -- granting clients direct write access to updated_at.
  update public.conversations
  set title = title
  where id = new.conversation_id
    and user_id = new.user_id;
  return new;
end;
$$;

revoke all on function public.bump_conversation_updated_at_from_message() from public, anon, authenticated;
