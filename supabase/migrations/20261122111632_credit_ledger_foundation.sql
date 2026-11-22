-- SULY credit ledger foundation for engine usage.
-- Accounts start at zero. No signup bonus, purchase, or live payment is implied.

create table public.credit_accounts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  available_credits bigint not null default 0 check (available_credits >= 0),
  reserved_credits bigint not null default 0 check (reserved_credits >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.credit_reservations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.credit_accounts(user_id) on delete cascade,
  task_id uuid not null,
  engine_run_id uuid not null,
  engine_id text not null check (engine_id in ('hermes-agent', 'opencode')),
  reserved_credits bigint not null check (reserved_credits between 1 and 1000000),
  settled_credits bigint,
  status text not null default 'reserved'
    check (status in ('reserved', 'settled', 'released')),
  idempotency_key text not null
    check (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9:_./-]{7,127}$'),
  expires_at timestamptz not null default (now() + interval '2 hours'),
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint credit_reservations_user_key_unique unique (user_id, idempotency_key),
  constraint credit_reservations_engine_run_unique unique (engine_run_id),
  constraint credit_reservations_id_user_unique unique (id, user_id),
  check (
    (status = 'reserved' and settled_credits is null and completed_at is null)
    or
    (status = 'settled' and settled_credits is not null
      and settled_credits between 0 and reserved_credits and completed_at is not null)
    or
    (status = 'released' and settled_credits is null and completed_at is not null)
  )
);

create table public.credit_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.credit_accounts(user_id) on delete cascade,
  reservation_id uuid,
  task_id uuid,
  engine_run_id uuid,
  engine_id text,
  transaction_type text not null
    check (transaction_type in ('grant', 'reserve', 'settle', 'release', 'expire')),
  available_delta bigint not null,
  reserved_delta bigint not null,
  idempotency_key text not null
    check (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9:_./-]{7,127}$'),
  metadata jsonb not null default '{}'::jsonb
    check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  constraint credit_ledger_user_key_unique unique (user_id, idempotency_key),
  constraint credit_ledger_reservation_owner_fkey
    foreign key (reservation_id, user_id)
    references public.credit_reservations(id, user_id) on delete cascade,
  check (
    (transaction_type = 'grant'
      and reservation_id is null and task_id is null and engine_run_id is null and engine_id is null
      and available_delta > 0 and reserved_delta = 0)
    or
    (transaction_type = 'reserve'
      and reservation_id is not null and task_id is not null and engine_run_id is not null and engine_id is not null
      and available_delta < 0 and reserved_delta = -available_delta)
    or
    (transaction_type = 'settle'
      and reservation_id is not null and task_id is not null and engine_run_id is not null and engine_id is not null
      and available_delta >= 0 and reserved_delta < 0
      and available_delta + reserved_delta <= 0)
    or
    (transaction_type in ('release', 'expire')
      and reservation_id is not null and task_id is not null and engine_run_id is not null and engine_id is not null
      and available_delta > 0 and reserved_delta = -available_delta)
  )
);

create index credit_ledger_user_created_idx
  on public.credit_ledger(user_id, created_at desc);
create index credit_ledger_reservation_idx
  on public.credit_ledger(reservation_id) where reservation_id is not null;
create index credit_reservations_user_status_idx
  on public.credit_reservations(user_id, status, created_at desc);
create index credit_reservations_expiry_idx
  on public.credit_reservations(expires_at)
  where status = 'reserved';

alter table public.credit_accounts enable row level security;
alter table public.credit_reservations enable row level security;
alter table public.credit_ledger enable row level security;

create policy credit_accounts_select_own on public.credit_accounts
  for select to authenticated using ((select auth.uid()) = user_id);
create policy credit_reservations_select_own on public.credit_reservations
  for select to authenticated using ((select auth.uid()) = user_id);
create policy credit_ledger_select_own on public.credit_ledger
  for select to authenticated using ((select auth.uid()) = user_id);

-- No direct writes for browser clients or service-role table clients.
-- Mutations are available only through the narrowly scoped SECURITY DEFINER RPCs below.
revoke all on public.credit_accounts, public.credit_reservations, public.credit_ledger
  from public, anon, authenticated, service_role;
grant select on public.credit_accounts, public.credit_reservations, public.credit_ledger
  to authenticated;

create or replace function public.grant_engine_credits(
  p_user_id uuid, p_amount bigint, p_reason text, p_idempotency_key text
)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_available bigint;
  v_existing public.credit_ledger%rowtype;
begin
  if p_user_id is null
     or p_amount is null or p_amount not between 1 and 1000000
     or p_reason is null or p_reason !~ '^[a-z][a-z0-9_.-]{0,79}$'
     or p_idempotency_key is null
     or p_idempotency_key !~ '^[A-Za-z0-9][A-Za-z0-9:_./-]{7,127}$' then
    raise exception 'engine_credit_grant_invalid';
  end if;

  insert into public.credit_accounts(user_id) values (p_user_id)
  on conflict (user_id) do nothing;

  select available_credits into v_available
    from public.credit_accounts where user_id = p_user_id for update;

  select * into v_existing from public.credit_ledger
   where user_id = p_user_id and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.transaction_type <> 'grant'
       or v_existing.available_delta <> p_amount
       or v_existing.metadata ->> 'reason' is distinct from p_reason then
      raise exception 'engine_credit_idempotency_conflict';
    end if;
    return v_available;
  end if;

  update public.credit_accounts
     set available_credits = available_credits + p_amount, updated_at = now()
   where user_id = p_user_id
   returning available_credits into v_available;

  insert into public.credit_ledger(
    user_id, transaction_type, available_delta, reserved_delta, idempotency_key, metadata
  ) values (
    p_user_id, 'grant', p_amount, 0, p_idempotency_key,
    jsonb_build_object('reason', p_reason)
  );
  return v_available;
end;
$$;

create or replace function public.reserve_engine_credits(
  p_user_id uuid, p_task_id uuid, p_engine_run_id uuid,
  p_engine_id text, p_amount bigint, p_idempotency_key text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_available bigint;
  v_run_status text;
  v_reservation public.credit_reservations%rowtype;
  v_reservation_id uuid;
begin
  if p_user_id is null or p_task_id is null or p_engine_run_id is null
     or p_engine_id is null or p_engine_id not in ('hermes-agent', 'opencode')
     or p_amount is null or p_amount not between 1 and 1000000
     or p_idempotency_key is null
     or p_idempotency_key !~ '^[A-Za-z0-9][A-Za-z0-9:_./-]{7,127}$' then
    raise exception 'engine_credit_reservation_invalid';
  end if;

  insert into public.credit_accounts(user_id) values (p_user_id)
  on conflict (user_id) do nothing;

  select available_credits into v_available
    from public.credit_accounts where user_id = p_user_id for update;

  select * into v_reservation
    from public.credit_reservations
   where user_id = p_user_id and idempotency_key = p_idempotency_key
   for update;
  if found then
    if v_reservation.task_id <> p_task_id
       or v_reservation.engine_run_id <> p_engine_run_id
       or v_reservation.engine_id <> p_engine_id
       or v_reservation.reserved_credits <> p_amount then
      raise exception 'engine_credit_idempotency_conflict';
    end if;
    return v_reservation.id;
  end if;

  select * into v_reservation
    from public.credit_reservations where engine_run_id = p_engine_run_id for update;
  if found then
    raise exception 'engine_run_already_has_credit_reservation';
  end if;

  select r.status into v_run_status
    from public.engine_runs r
    join public.tasks t on t.id = r.task_id and t.user_id = r.user_id
   where r.id = p_engine_run_id and r.task_id = p_task_id
     and r.user_id = p_user_id and r.engine_id = p_engine_id
     and r.status = 'running' and t.status = 'running'
     and t.cancel_requested_at is null
   for update of r, t;
  if not found then
    raise exception 'engine_credit_run_not_reservable';
  end if;
  if v_available < p_amount then
    raise exception 'insufficient_engine_credits';
  end if;

  update public.credit_accounts
     set available_credits = available_credits - p_amount,
         reserved_credits = reserved_credits + p_amount,
         updated_at = now()
   where user_id = p_user_id;

  insert into public.credit_reservations(
    user_id, task_id, engine_run_id, engine_id, reserved_credits, idempotency_key
  ) values (
    p_user_id, p_task_id, p_engine_run_id, p_engine_id, p_amount, p_idempotency_key
  ) returning id into v_reservation_id;

  insert into public.credit_ledger(
    user_id, reservation_id, task_id, engine_run_id, engine_id,
    transaction_type, available_delta, reserved_delta, idempotency_key, metadata
  ) values (
    p_user_id, v_reservation_id, p_task_id, p_engine_run_id, p_engine_id,
    'reserve', -p_amount, p_amount, p_idempotency_key,
    jsonb_build_object('reserved_credits', p_amount)
  );
  return v_reservation_id;
end;
$$;

create or replace function public.settle_engine_credits(
  p_user_id uuid, p_reservation_id uuid, p_actual_credits bigint, p_idempotency_key text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_reservation public.credit_reservations%rowtype;
  v_existing public.credit_ledger%rowtype;
  v_refund bigint;
begin
  if p_user_id is null or p_reservation_id is null
     or p_actual_credits is null or p_actual_credits not between 0 and 1000000
     or p_idempotency_key is null
     or p_idempotency_key !~ '^[A-Za-z0-9][A-Za-z0-9:_./-]{7,127}$' then
    raise exception 'engine_credit_settlement_invalid';
  end if;

  perform 1 from public.credit_accounts where user_id = p_user_id for update;
  if not found then raise exception 'engine_credit_account_not_found'; end if;

  select * into v_reservation from public.credit_reservations
   where id = p_reservation_id and user_id = p_user_id for update;
  if not found then raise exception 'engine_credit_reservation_not_found'; end if;

  select * into v_existing from public.credit_ledger
   where user_id = p_user_id and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.transaction_type <> 'settle'
       or v_existing.reservation_id <> p_reservation_id
       or v_existing.metadata ->> 'actual_credits' is distinct from p_actual_credits::text then
      raise exception 'engine_credit_idempotency_conflict';
    end if;
    return true;
  end if;

  if v_reservation.status <> 'reserved' then
    raise exception 'engine_credit_reservation_already_finalized';
  end if;
  if p_actual_credits > v_reservation.reserved_credits then
    raise exception 'engine_credit_overrun';
  end if;
  if exists (
    select 1 from public.engine_runs
     where id = v_reservation.engine_run_id and user_id = p_user_id and status = 'running'
  ) then
    raise exception 'engine_credit_run_still_running';
  end if;

  v_refund := v_reservation.reserved_credits - p_actual_credits;
  update public.credit_accounts
     set available_credits = available_credits + v_refund,
         reserved_credits = reserved_credits - v_reservation.reserved_credits,
         updated_at = now()
   where user_id = p_user_id;
  update public.credit_reservations
     set status = 'settled', settled_credits = p_actual_credits, completed_at = now()
   where id = p_reservation_id and user_id = p_user_id;

  insert into public.credit_ledger(
    user_id, reservation_id, task_id, engine_run_id, engine_id,
    transaction_type, available_delta, reserved_delta, idempotency_key, metadata
  ) values (
    p_user_id, p_reservation_id, v_reservation.task_id, v_reservation.engine_run_id,
    v_reservation.engine_id, 'settle', v_refund, -v_reservation.reserved_credits,
    p_idempotency_key, jsonb_build_object('actual_credits', p_actual_credits)
  );
  return true;
end;
$$;

create or replace function public.release_engine_credits(
  p_user_id uuid, p_reservation_id uuid, p_reason text, p_idempotency_key text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_reservation public.credit_reservations%rowtype;
  v_existing public.credit_ledger%rowtype;
begin
  if p_user_id is null or p_reservation_id is null
     or p_reason is null or p_reason !~ '^[a-z][a-z0-9_.-]{0,79}$'
     or p_idempotency_key is null
     or p_idempotency_key !~ '^[A-Za-z0-9][A-Za-z0-9:_./-]{7,127}$' then
    raise exception 'engine_credit_release_invalid';
  end if;

  perform 1 from public.credit_accounts where user_id = p_user_id for update;
  if not found then raise exception 'engine_credit_account_not_found'; end if;

  select * into v_reservation from public.credit_reservations
   where id = p_reservation_id and user_id = p_user_id for update;
  if not found then raise exception 'engine_credit_reservation_not_found'; end if;

  select * into v_existing from public.credit_ledger
   where user_id = p_user_id and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.transaction_type <> 'release'
       or v_existing.reservation_id <> p_reservation_id
       or v_existing.metadata ->> 'reason' is distinct from p_reason then
      raise exception 'engine_credit_idempotency_conflict';
    end if;
    return true;
  end if;

  if v_reservation.status <> 'reserved' then
    raise exception 'engine_credit_reservation_already_finalized';
  end if;
  if exists (
    select 1 from public.engine_runs
     where id = v_reservation.engine_run_id and user_id = p_user_id and status = 'running'
  ) then
    raise exception 'engine_credit_run_still_running';
  end if;

  update public.credit_accounts
     set available_credits = available_credits + v_reservation.reserved_credits,
         reserved_credits = reserved_credits - v_reservation.reserved_credits,
         updated_at = now()
   where user_id = p_user_id;
  update public.credit_reservations
     set status = 'released', completed_at = now()
   where id = p_reservation_id and user_id = p_user_id;

  insert into public.credit_ledger(
    user_id, reservation_id, task_id, engine_run_id, engine_id,
    transaction_type, available_delta, reserved_delta, idempotency_key, metadata
  ) values (
    p_user_id, p_reservation_id, v_reservation.task_id, v_reservation.engine_run_id,
    v_reservation.engine_id, 'release', v_reservation.reserved_credits,
    -v_reservation.reserved_credits, p_idempotency_key, jsonb_build_object('reason', p_reason)
  );
  return true;
end;
$$;

create or replace function public.release_expired_engine_credit_reservations(
  p_batch_size integer default 25
)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_candidate record;
  v_reservation public.credit_reservations%rowtype;
  v_released integer := 0;
begin
  if p_batch_size is null or p_batch_size not between 1 and 100 then
    raise exception 'engine_credit_expiry_batch_invalid';
  end if;

  for v_candidate in
    select r.id, r.user_id
      from public.credit_reservations r
     where r.status = 'reserved' and r.expires_at <= now()
       and not exists (
         select 1 from public.engine_runs er
          where er.id = r.engine_run_id and er.user_id = r.user_id
            and er.status = 'running'
       )
     order by r.expires_at
     limit p_batch_size
  loop
    -- Keep the same lock order as settle/release: account first, reservation second.
    perform 1 from public.credit_accounts
     where user_id = v_candidate.user_id for update;

    select * into v_reservation from public.credit_reservations
     where id = v_candidate.id and user_id = v_candidate.user_id
       and status = 'reserved' and expires_at <= now()
     for update skip locked;
    if not found then continue; end if;

    update public.credit_accounts
       set available_credits = available_credits + v_reservation.reserved_credits,
           reserved_credits = reserved_credits - v_reservation.reserved_credits,
           updated_at = now()
     where user_id = v_reservation.user_id;
    update public.credit_reservations
       set status = 'released', completed_at = now()
     where id = v_reservation.id and user_id = v_reservation.user_id;

    insert into public.credit_ledger(
      user_id, reservation_id, task_id, engine_run_id, engine_id,
      transaction_type, available_delta, reserved_delta, idempotency_key, metadata
    ) values (
      v_reservation.user_id, v_reservation.id, v_reservation.task_id,
      v_reservation.engine_run_id, v_reservation.engine_id,
      'expire', v_reservation.reserved_credits, -v_reservation.reserved_credits,
      'expiry:' || v_reservation.id::text,
      jsonb_build_object('reason', 'expired_reservation')
    );
    v_released := v_released + 1;
  end loop;
  return v_released;
end;
$$;

revoke all on function public.grant_engine_credits(uuid, bigint, text, text)
  from public, anon, authenticated;
revoke all on function public.reserve_engine_credits(uuid, uuid, uuid, text, bigint, text)
  from public, anon, authenticated;
revoke all on function public.settle_engine_credits(uuid, uuid, bigint, text)
  from public, anon, authenticated;
revoke all on function public.release_engine_credits(uuid, uuid, text, text)
  from public, anon, authenticated;
revoke all on function public.release_expired_engine_credit_reservations(integer)
  from public, anon, authenticated;

grant execute on function public.grant_engine_credits(uuid, bigint, text, text) to service_role;
grant execute on function public.reserve_engine_credits(uuid, uuid, uuid, text, bigint, text) to service_role;
grant execute on function public.settle_engine_credits(uuid, uuid, bigint, text) to service_role;
grant execute on function public.release_engine_credits(uuid, uuid, text, text) to service_role;
grant execute on function public.release_expired_engine_credit_reservations(integer) to service_role;

comment on table public.credit_accounts is
  'SULY server-managed credit totals. Browser clients can only read their own account; balances start at zero.';
comment on table public.credit_reservations is
  'Idempotent task-attempt holds. Expiry reconciliation releases only after the linked engine run is no longer running.';
comment on table public.credit_ledger is
  'Owner-readable, server-written credit deltas. Browser and service-role table writes are revoked.';
