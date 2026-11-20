-- Atomic compare-and-swap application of an approved OpenCode change set.
-- The function is callable only by the trusted service_role API worker.
begin;

create extension if not exists pgcrypto with schema extensions;

create or replace function public.apply_opencode_change_set(
  p_user_id uuid,
  p_change_set_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_set public.opencode_change_sets%rowtype;
  v_current_revision text;
  v_change jsonb;
  v_action text;
  v_path text;
  v_content text;
  v_expected_hash text;
  v_rows integer;
begin
  if current_user <> 'service_role' then
    raise exception 'service_role_required' using errcode = '42501';
  end if;

  select * into v_set
  from public.opencode_change_sets
  where id = p_change_set_id and user_id = p_user_id
  for update;

  if not found or v_set.status <> 'review_ready' then
    return jsonb_build_object('applied', false, 'reason', 'change_set_not_reviewable');
  end if;

  if not exists (
    select 1 from public.projects
    where id = v_set.project_id and user_id = p_user_id
  ) then
    raise exception 'project_not_owned' using errcode = '42501';
  end if;

  select encode(
    extensions.digest(
      convert_to(coalesce(string_agg(
        path || chr(0) ||
        encode(extensions.digest(convert_to(content, 'UTF8'), 'sha256'), 'hex') ||
        chr(10), '' order by path
      ), ''), 'UTF8'),
      'sha256'
    ), 'hex'
  )
  into v_current_revision
  from public.project_files
  where project_id = v_set.project_id and user_id = p_user_id;

  if v_current_revision is distinct from v_set.base_revision then
    update public.opencode_change_sets
    set status = 'stale', decided_at = now()
    where id = v_set.id and user_id = p_user_id;
    return jsonb_build_object('applied', false, 'reason', 'workspace_revision_conflict');
  end if;

  if jsonb_typeof(v_set.changes) <> 'array' or jsonb_array_length(v_set.changes) > 500 then
    raise exception 'changeset_invalid';
  end if;

  update public.opencode_change_sets
  set status = 'applying'
  where id = v_set.id and user_id = p_user_id and status = 'review_ready';

  if not found then
    return jsonb_build_object('applied', false, 'reason', 'change_set_claim_lost');
  end if;

  for v_change in select value from jsonb_array_elements(v_set.changes)
  loop
    v_action := v_change ->> 'action';
    v_path := v_change ->> 'path';

    if v_path is null or length(v_path) < 1 or length(v_path) > 512
       or left(v_path, 1) = '/'
       or v_path like '%\%'
       or v_path ~ '(^|/)\.\.?(/|$)'
       or v_path ~* '(^|/)(\.git|node_modules|\.suly|__pycache__)(/|$)'
       or v_path ~* '(^|/)\.env'
    then
      raise exception 'changeset_path_invalid';
    end if;

    if v_action = 'delete' then
      if (select count(*) from jsonb_object_keys(v_change)) <> 2 then
        raise exception 'changeset_delete_payload_invalid';
      end if;
      delete from public.project_files
      where project_id = v_set.project_id and user_id = p_user_id and path = v_path;
      get diagnostics v_rows = row_count;
      if v_rows <> 1 then
        raise exception 'changeset_delete_target_missing';
      end if;
    elsif v_action in ('create', 'update') then
      v_content := v_change ->> 'content';
      v_expected_hash := v_change ->> 'sha256';
      if v_content is null or octet_length(v_content) > 262144
         or v_expected_hash is null
         or v_expected_hash !~ '^[0-9a-f]{64}$'
         or encode(extensions.digest(convert_to(v_content, 'UTF8'), 'sha256'), 'hex') <> v_expected_hash
      then
        raise exception 'changeset_content_invalid';
      end if;
      if v_action = 'create' then
        insert into public.project_files(project_id, user_id, path, content, size_bytes)
        values (v_set.project_id, p_user_id, v_path, v_content, octet_length(v_content));
      else
        update public.project_files
        set content = v_content, size_bytes = octet_length(v_content), updated_at = now()
        where project_id = v_set.project_id and user_id = p_user_id and path = v_path;
        get diagnostics v_rows = row_count;
        if v_rows <> 1 then
          raise exception 'changeset_update_target_missing';
        end if;
      end if;
    else
      raise exception 'changeset_action_invalid';
    end if;
  end loop;

  update public.opencode_change_sets
  set status = 'applied', decided_at = now()
  where id = v_set.id and user_id = p_user_id and status = 'applying';

  return jsonb_build_object('applied', true, 'change_set_id', v_set.id);
end;
$$;

revoke all on function public.apply_opencode_change_set(uuid, uuid) from public, anon, authenticated;
grant execute on function public.apply_opencode_change_set(uuid, uuid) to service_role;

commit;
