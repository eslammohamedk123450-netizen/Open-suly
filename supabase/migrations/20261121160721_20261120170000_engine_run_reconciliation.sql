-- Reconcile an engine attempt when its owning task-step lease ends unexpectedly.
-- هذه الهجرة لا تشغّل أي محرك؛ إنها تمنع بقاء سجل المحاولة بحالة running بعد انتهاء ملكية الخطوة.

-- ننشئ دالة داخل قاعدة البيانات لمزامنة سجل المحرك مع انتقال حالة الخطوة.
create or replace function public.reconcile_engine_run_on_step_transition()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  -- نحتفظ بعلامة الإلغاء حتى لا نحول الإلغاء المقصود إلى فشل.
  v_cancel_requested boolean := false;
  -- نحدد رمزًا آمنًا لا يحتوي على prompt أو أسرار أو تفاصيل مزود الخدمة.
  v_safe_error_code text;
begin
  -- لا نحتاج إلى مصالحة إذا لم تكن الخطوة مملوكة لمحاولة تشغيل سابقة.
  if old.status <> 'running' then
    return new;
  end if;

  -- تحديث heartbeat يغير وقت انتهاء الإيجار فقط، ولا ينهي المحاولة.
  if new.status = 'running'
     and new.lease_token is not distinct from old.lease_token then
    return new;
  end if;

  -- نقرأ طلب الإلغاء من المهمة الأم، وليس من بيانات يرسلها العميل.
  select (t.cancel_requested_at is not null)
    into v_cancel_requested
    from public.tasks t
   where t.id = old.task_id
     and t.user_id = old.user_id;

  -- نختار رمزًا عامًا وآمنًا حسب سبب انتهاء الخطوة.
  if coalesce(v_cancel_requested, false) or new.status = 'cancelled' then
    v_safe_error_code := null;
  elsif old.lease_expires_at is not null
        and old.lease_expires_at <= now() then
    v_safe_error_code := 'engine_lease_expired';
  else
    v_safe_error_code := 'engine_step_ended';
  end if;

  -- ننهي المحاولة المطابقة فقط، ولا نلمس محاولة سابقة أو محاولة جديدة.
  update public.engine_runs r
     set status = case
           when coalesce(v_cancel_requested, false) or new.status = 'cancelled'
             then 'cancelled'
           else 'failed'
         end,
         error_code = v_safe_error_code,
         completed_at = coalesce(r.completed_at, now()),
         updated_at = now()
   where r.step_id = old.id
     and r.task_id = old.task_id
     and r.user_id = old.user_id
     and r.attempt_count = old.attempt_count
     and r.status = 'running';

  -- نسمح بتكملة تحديث الخطوة الأصلي.
  return new;
end;
$$;

-- نربط المصالحة بتغييرات الحالة والـlease فقط.
drop trigger if exists task_steps_reconcile_engine_run on public.task_steps;
create trigger task_steps_reconcile_engine_run
after update of status, lease_token, lease_expires_at
on public.task_steps
for each row
execute function public.reconcile_engine_run_on_step_transition();

-- دالة الـtrigger ليست واجهة API ولا يجب استدعاؤها مباشرة من أدوار التطبيق.
revoke all on function public.reconcile_engine_run_on_step_transition()
  from public, anon, authenticated;
-- نمنح دور الخادم فقط صلاحية الدالة؛ المستخدمون لا يستدعونها عبر Data API.
grant execute on function public.reconcile_engine_run_on_step_transition()
  to service_role;

-- نثبت سبب المصالحة في وصف الدالة ليسهل على فريق التطوير فهمها.
comment on function public.reconcile_engine_run_on_step_transition() is
  'Closes only the matching running engine attempt when its task-step lease ends, expires, or is cancelled. Stores safe error codes only.';
