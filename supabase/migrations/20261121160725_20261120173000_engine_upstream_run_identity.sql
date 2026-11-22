-- Persist the upstream Hermes run identity without storing prompts or output.
-- نخزن معرف التشغيل الخارجي فقط لربط سجل SULY بالمحرك الأصلي.

-- نضيف عمودًا محدود الطول لمعرف التشغيل القادم من Hermes.
alter table public.engine_runs
  add column if not exists upstream_run_id text
  check (
    upstream_run_id is null
    or char_length(upstream_run_id) between 1 and 128
  );

-- نمنع ربط نفس تشغيل Hermes بأكثر من سجل محاولة داخل نفس المحرك.
create unique index if not exists engine_runs_upstream_identity_idx
  on public.engine_runs(engine_id, upstream_run_id)
  where upstream_run_id is not null;

-- نربط المعرف الخارجي بالمحاولة بشرط أن العامل ما زال يملك lease صالحًا.
create or replace function public.attach_engine_upstream_run(
  p_run_id uuid,
  p_step_id uuid,
  p_lease_token uuid,
  p_upstream_run_id text
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rows integer;
begin
  -- نرفض المعرفات الفارغة أو الطويلة حتى لا نخزن بيانات عشوائية.
  if p_upstream_run_id is null
     or char_length(btrim(p_upstream_run_id)) not between 1 and 128 then
    raise exception 'invalid_upstream_run_id';
  end if;

  -- نربط المعرف فقط بسجل المحاولة المطابق للخطوة والـlease الحالي.
  update public.engine_runs r
     set upstream_run_id = p_upstream_run_id,
         updated_at = now()
    from public.task_steps s
   where r.id = p_run_id
     and r.step_id = p_step_id
     and s.id = r.step_id
     and s.task_id = r.task_id
     and s.user_id = r.user_id
     and s.status = 'running'
     and s.lease_token = p_lease_token
     and s.lease_expires_at > now()
     and r.status = 'running'
     and (r.upstream_run_id is null or r.upstream_run_id = p_upstream_run_id)
     and not exists (
       select 1
         from public.tasks t
        where t.id = s.task_id
          and t.cancel_requested_at is not null
     );

  -- نعيد true فقط إذا تم تحديث سجل واحد بالضبط.
  get diagnostics v_rows = row_count;
  return v_rows = 1;
end;
$$;

-- لا نسمح للعميل أو المستخدم المجهول باستدعاء RPC الخاصة بالخادم.
revoke all on function public.attach_engine_upstream_run(uuid,uuid,uuid,text)
  from public, anon, authenticated;
grant execute on function public.attach_engine_upstream_run(uuid,uuid,uuid,text)
  to service_role;

-- نوثق أن الحقل لا يحتوي على أي محتوى محادثة أو أسرار.
comment on column public.engine_runs.upstream_run_id is
  'Opaque upstream engine run identifier only; never a prompt, output, or credential.';
