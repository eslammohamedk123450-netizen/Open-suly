-- Alert on external runs whose upstream identity was lost before it could be persisted.
-- لا نخفي التشغيل اليتيم الذي لا نملك معرفه الخارجي؛ نعرض عدّادًا للخادم للمراقبة.

create index if not exists engine_runs_stop_pending_missing_identity_idx
  on public.engine_runs(started_at)
  where status = 'stop_pending' and upstream_run_id is null;

create or replace function public.count_engine_runs_missing_upstream_identity(
  p_min_age_seconds integer default 30
)
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_count integer;
begin
  if p_min_age_seconds is null or p_min_age_seconds not between 1 and 3600 then
    raise exception 'invalid_missing_identity_age';
  end if;

  select count(*)::integer
    into v_count
    from public.engine_runs r
   where r.status = 'stop_pending'
     and r.upstream_run_id is null
     and r.started_at <= now() - make_interval(secs => p_min_age_seconds);

  return v_count;
end;
$$;

revoke all on function public.count_engine_runs_missing_upstream_identity(integer)
  from public, anon, authenticated;
grant execute on function public.count_engine_runs_missing_upstream_identity(integer)
  to service_role;

comment on function public.count_engine_runs_missing_upstream_identity(integer) is
  'Service-only count of stop_pending external engine attempts whose upstream run ID was not persisted before lease loss.';
