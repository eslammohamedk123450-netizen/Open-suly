-- Keep the profile display name in sync with the metadata submitted by the client.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    coalesce(
      nullif(trim(coalesce(new.raw_user_meta_data ->> 'display_name', '')), ''),
      nullif(trim(coalesce(new.raw_user_meta_data ->> 'name', '')), '')
    )
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

revoke all on function public.handle_new_user() from public, anon, authenticated;
