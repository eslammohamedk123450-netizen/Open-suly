-- pgcrypto is installed in the extensions schema. The function intentionally
-- uses an empty search_path, so qualify the extension function explicitly.
create or replace function public.apply_opencode_change_set(p_user_id uuid, p_change_set_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  cs public.opencode_change_sets%rowtype;
  actual_revision text;
  revision_payload bytea;
  item jsonb;
  file_path text;
  action_name text;
  file_content text;
  expected_sha text;
begin
  select * into cs from public.opencode_change_sets
   where id=p_change_set_id and user_id=p_user_id and status='review_ready'
   for update;
  if not found then return jsonb_build_object('applied',false,'reason','not_reviewable'); end if;

  select coalesce(string_agg(
      convert_to(pf.path,'UTF8') || decode('00','hex') ||
      convert_to(encode(extensions.digest(convert_to(pf.content,'UTF8'),'sha256'),'hex'),'UTF8') ||
      decode('0a','hex'), ''::bytea order by pf.path
    ), ''::bytea)
    into revision_payload
    from public.project_files pf
   where pf.project_id=cs.project_id and pf.user_id=p_user_id;
  actual_revision := encode(extensions.digest(coalesce(revision_payload,''::bytea),'sha256'),'hex');
  if actual_revision <> cs.base_revision then
    update public.opencode_change_sets set status='stale' where id=cs.id;
    return jsonb_build_object('applied',false,'reason','stale_revision','current_revision',actual_revision);
  end if;

  update public.opencode_change_sets set status='applying' where id=cs.id and status='review_ready';
  if not found then return jsonb_build_object('applied',false,'reason','claim_conflict'); end if;

  for item in select value from jsonb_array_elements(cs.changes)
  loop
    file_path := item->>'path';
    action_name := item->>'action';
    if file_path is null or file_path='' or file_path like '/%' or file_path ~ '(^|/)\.\.(/|$)' or file_path like '%\\%' then
      raise exception 'invalid_change_path';
    end if;
    if action_name in ('create','update') then
      file_content := item->>'content';
      expected_sha := encode(extensions.digest(convert_to(file_content,'UTF8'),'sha256'),'hex');
      if expected_sha <> item->>'sha256' then raise exception 'change_digest_mismatch'; end if;
      insert into public.project_files(project_id,user_id,path,content,size_bytes,updated_at)
      values(cs.project_id,p_user_id,file_path,file_content,octet_length(file_content),now())
      on conflict(project_id,path) do update set
        content=excluded.content,size_bytes=excluded.size_bytes,updated_at=now()
      where project_files.user_id=p_user_id;
    elsif action_name='delete' then
      delete from public.project_files where project_id=cs.project_id and user_id=p_user_id and path=file_path;
    else
      raise exception 'invalid_change_action';
    end if;
  end loop;

  update public.opencode_change_sets set status='applied',decided_at=now() where id=cs.id;
  update public.opencode_task_runs set status='completed',finished_at=now(),updated_at=now()
   where id=cs.run_id and user_id=p_user_id and status in ('review_ready','applying');
  return jsonb_build_object('applied',true,'change_set_id',cs.id);
exception when others then
  update public.opencode_change_sets set status='failed' where id=p_change_set_id and user_id=p_user_id;
  raise;
end;
$$;
revoke all on function public.apply_opencode_change_set(uuid,uuid) from public, anon, authenticated;
grant execute on function public.apply_opencode_change_set(uuid,uuid) to service_role;
