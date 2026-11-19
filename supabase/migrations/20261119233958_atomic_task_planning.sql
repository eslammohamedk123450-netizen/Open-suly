create or replace function public.plan_task(
  p_task_id uuid,
  p_user_id uuid,
  p_steps jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_task public.tasks%rowtype;
  v_step jsonb;
  v_key text;
  v_title text;
  v_description text;
  v_dep jsonb;
  v_input jsonb;
  v_keys text[] := array[]::text[];
  v_order integer := 0;
  v_count integer;
begin
  if jsonb_typeof(p_steps) <> 'array' then
    raise exception 'plan_must_be_array' using errcode = '22023';
  end if;
  v_count := jsonb_array_length(p_steps);
  if v_count < 1 or v_count > 50 then
    raise exception 'plan_step_count_out_of_range' using errcode = '22023';
  end if;
  select * into v_task from public.tasks
  where id = p_task_id and user_id = p_user_id for update;
  if not found then
    raise exception 'task_not_found' using errcode = 'P0002';
  end if;
  if v_task.status <> 'queued' or exists (
    select 1 from public.task_steps where task_id = p_task_id
  ) then
    raise exception 'task_already_planned' using errcode = '55000';
  end if;
  for v_step in select value from jsonb_array_elements(p_steps)
  loop
    v_key := v_step->>'step_key';
    v_title := v_step->>'title';
    v_description := coalesce(v_step->>'description', '');
    v_dep := coalesce(v_step->'depends_on', '[]'::jsonb);
    v_input := coalesce(v_step->'input', '{}'::jsonb);
    if v_key is null or char_length(v_key) not between 1 and 100
       or v_title is null or char_length(btrim(v_title)) not between 1 and 200
       or jsonb_typeof(v_dep) <> 'array' or jsonb_typeof(v_input) <> 'object'
       or char_length(v_description) > 4000 then
      raise exception 'invalid_step_definition' using errcode = '22023';
    end if;
    if v_key = any(v_keys) then
      raise exception 'duplicate_step_key' using errcode = '22023';
    end if;
    if exists (
      select 1 from jsonb_array_elements_text(v_dep) dep(key)
      where not (dep.key = any(v_keys))
    ) then
      raise exception 'dependency_must_reference_prior_step' using errcode = '22023';
    end if;
    insert into public.task_steps (
      task_id,user_id,step_key,title,description,step_order,depends_on,input
    ) values (
      p_task_id,p_user_id,v_key,btrim(v_title),v_description,v_order,v_dep,v_input
    );
    v_keys := array_append(v_keys, v_key);
    v_order := v_order + 1;
  end loop;
  update public.tasks set plan = p_steps, status = 'ready'
  where id = p_task_id and user_id = p_user_id;
  return jsonb_build_object('task_id',p_task_id,'status','ready','step_count',v_count);
end;
$$;
revoke all on function public.plan_task(uuid, uuid, jsonb) from public, anon, authenticated;
grant execute on function public.plan_task(uuid, uuid, jsonb) to service_role;
