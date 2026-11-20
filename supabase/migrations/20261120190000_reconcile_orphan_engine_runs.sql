-- Periodic safety net for engine attempts whose lease transition was not observed.
-- هذه الدالة مصالحة احتياطية محدودة الدفعة؛ لا تشغّل محركات ولا تتصل بها.

create or replace function public.reconcile_orphan_engine_runs(
  p_batch_size integer default 100
)
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rows integer;
begin
  if p_batch_size is null or p_batch_size not between 1 and 500 then
    raise exception 'invalid_reconciliation_batch_size';
  end if;

  -- نختار سجلات التشغيل العالقة فقط، مع قفل متجاوز للسجلات التي يعالجها عامل آخر.
  with candidates as (
    select r.id,
           (t.cancel_requested_at is not null or s.status = 'cancelled') as was_cancelled
      from public.engine_runs r
      join public.task_steps s
        on s.id = r.step_id
       and s.task_id = r.task_id
       and s.user_id = r.user_id
      join public.tasks t
        on t.id = s.task_id
       and t.user_id = s.user_id
     where r.status = 'running'
       and (
         s.status <> 'running'
         or s.lease_expires_at is null
         or s.lease_expires_at <= now()
         or t.cancel_requested_at is not null
       )
     order by r.started_at, r.id
     for update of r skip locked
     limit p_batch_size
  )
  update public.engine_runs r
     set status = case when c.was_cancelled then 'cancelled' else 'failed' end,
         error_code = case
           when c.was_cancelled then null
           when exists (
             select 1 from public.task_steps s
              where s.id = r.step_id
                and s.lease_expires_at is not null
                and s.lease_expires_at <= now()
           ) then 'engine_lease_expired'
           else 'engine_step_ended'
         end,
         completed_at = coalesce(r.completed_at, now()),
         updated_at = now()
    from candidates c
   where r.id = c.id
     and r.status = 'running';

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

revoke all on function public.reconcile_orphan_engine_runs(integer)
  from public, anon, authenticated;
grant execute on function public.reconcile_orphan_engine_runs(integer)
  to service_role;

comment on function public.reconcile_orphan_engine_runs(integer) is
  'Bounded service-only reconciliation of running engine attempts whose owning task step is cancelled, terminal, or has an expired lease.';
