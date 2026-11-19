-- Keep conversation ordering current whenever the owner sends a message.
create or replace function public.bump_conversation_updated_at_from_message()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  update public.conversations
  set updated_at = now()
  where id = new.conversation_id
    and user_id = new.user_id;
  return new;
end;
$$;

revoke all on function public.bump_conversation_updated_at_from_message() from public, anon, authenticated;
grant update (updated_at) on public.conversations to authenticated;

create trigger messages_bump_conversation_updated_at
  after insert on public.messages
  for each row execute function public.bump_conversation_updated_at_from_message();
