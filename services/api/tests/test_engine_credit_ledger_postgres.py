"""اختبارات ledger حقيقية على PostgreSQL disposable فقط؛ لا تتصل ببيئة SULY."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "20261121250000_credit_ledger_foundation.sql"
)


@pytest.fixture(scope="module")
def credit_test_dsn():
    dsn = os.environ.get("SULY_CREDIT_TEST_DSN")
    if not dsn:
        pytest.skip("SULY_CREDIT_TEST_DSN is required for disposable PostgreSQL integration")
    if os.environ.get("SULY_CREDIT_TEST_ALLOW_RESET") != "1":
        pytest.skip("Set SULY_CREDIT_TEST_ALLOW_RESET=1 only for a disposable test database")

    import psycopg

    connection = psycopg.connect(dsn, autocommit=True)
    # تجهيز auth/RLS والجدولَين المرتبطَين بالـengine-run، بصورة مصغرة ومؤقتة.
    connection.execute("create schema if not exists auth")
    connection.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            CREATE ROLE anon NOLOGIN;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            CREATE ROLE authenticated NOLOGIN;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
            CREATE ROLE service_role NOLOGIN BYPASSRLS;
          END IF;
        END $$;
        """,
        prepare=False,
    )
    connection.execute("alter role service_role bypassrls")
    connection.execute(
        "create table if not exists auth.users (id uuid primary key)"
    )
    connection.execute(
        """
        create or replace function auth.uid()
        returns uuid
        language sql
        stable
        as $$
          select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
        $$;
        """,
        prepare=False,
    )
    connection.execute("grant usage on schema auth to authenticated")
    connection.execute("grant execute on function auth.uid() to authenticated")
    connection.execute(
        """
        create table if not exists public.tasks (
          id uuid primary key,
          user_id uuid not null references auth.users(id),
          status text not null,
          cancel_requested_at timestamptz,
          unique (id, user_id)
        );
        """,
        prepare=False,
    )
    connection.execute(
        """
        create table if not exists public.engine_runs (
          id uuid primary key,
          task_id uuid not null,
          user_id uuid not null,
          engine_id text not null,
          status text not null
        );
        """,
        prepare=False,
    )
    # نعيد بناء ledger داخل قاعدة الاختبار فقط حتى يمكن إعادة تشغيل هذا الملف.
    connection.execute("drop function if exists public.grant_engine_credits(uuid,bigint,text,text) cascade")
    connection.execute("drop function if exists public.reserve_engine_credits(uuid,uuid,uuid,text,bigint,text) cascade")
    connection.execute("drop function if exists public.settle_engine_credits(uuid,uuid,bigint,text) cascade")
    connection.execute("drop function if exists public.release_engine_credits(uuid,uuid,text,text) cascade")
    connection.execute("drop function if exists public.release_expired_engine_credit_reservations(integer) cascade")
    connection.execute("drop table if exists public.credit_ledger cascade")
    connection.execute("drop table if exists public.credit_reservations cascade")
    connection.execute("drop table if exists public.credit_accounts cascade")
    connection.execute(MIGRATION.read_text(encoding="utf-8"), prepare=False)
    yield dsn
    connection.close()


@pytest.fixture
def credit_db(credit_test_dsn):
    import psycopg

    connection = psycopg.connect(credit_test_dsn, autocommit=True)
    connection.execute(
        "truncate public.credit_ledger, public.credit_reservations, public.credit_accounts, "
        "public.engine_runs, public.tasks, auth.users cascade"
    )
    yield connection
    connection.close()


def _seed_run(connection, user_id, task_id, run_id, engine_id="opencode"):
    connection.execute("insert into auth.users (id) values (%s) on conflict (id) do nothing", (user_id,))
    connection.execute(
        "insert into public.tasks (id,user_id,status,cancel_requested_at) values (%s,%s,'running',null)",
        (task_id, user_id),
    )
    connection.execute(
        "insert into public.engine_runs (id,task_id,user_id,engine_id,status) values (%s,%s,%s,%s,'running')",
        (run_id, task_id, user_id, engine_id),
    )


def _service_rpc(connection, query, args):
    # في CI نختبر صلاحيات service_role؛ لا نستخدم role المالك مباشرة.
    with connection.transaction():
        connection.execute("set local role service_role")
        return connection.execute(query, args).fetchone()[0]


def _grant(connection, user_id, amount, key, reason="test_grant"):
    return _service_rpc(
        connection,
        "select public.grant_engine_credits(%s,%s,%s,%s)",
        (user_id, amount, reason, key),
    )


def _reserve(connection, user_id, task_id, run_id, engine_id, amount, key):
    return _service_rpc(
        connection,
        "select public.reserve_engine_credits(%s,%s,%s,%s,%s,%s)",
        (user_id, task_id, run_id, engine_id, amount, key),
    )


def _account(connection, user_id):
    return connection.execute(
        "select available_credits,reserved_credits from public.credit_accounts where user_id=%s",
        (user_id,),
    ).fetchone()


def _ledger_types(connection, user_id):
    return connection.execute(
        "select transaction_type from public.credit_ledger where user_id=%s",
        (user_id,),
    ).fetchall()


def test_grant_reserve_settle_is_idempotent_and_refunds_unused_hold(credit_db):
    user_id, task_id, run_id = str(uuid4()), str(uuid4()), str(uuid4())
    _seed_run(credit_db, user_id, task_id, run_id)
    assert _grant(credit_db, user_id, 200, "grant:integration:001") == 200
    assert _grant(credit_db, user_id, 200, "grant:integration:001") == 200
    with pytest.raises(Exception, match="engine_credit_idempotency_conflict"):
        _grant(credit_db, user_id, 201, "grant:integration:001")

    reservation_id = _reserve(
        credit_db, user_id, task_id, run_id, "opencode", 120, "reserve:integration:001",
    )
    assert str(_reserve(
        credit_db, user_id, task_id, run_id, "opencode", 120, "reserve:integration:001",
    )) == str(reservation_id)
    assert _account(credit_db, user_id) == (80, 120)

    credit_db.execute("update public.engine_runs set status='succeeded' where id=%s", (run_id,))
    settle_args = (user_id, reservation_id, 70, "settle:integration:001")
    assert _service_rpc(credit_db, "select public.settle_engine_credits(%s,%s,%s,%s)", settle_args)
    assert _service_rpc(credit_db, "select public.settle_engine_credits(%s,%s,%s,%s)", settle_args)
    with pytest.raises(Exception, match="engine_credit_idempotency_conflict"):
        _service_rpc(
            credit_db,
            "select public.settle_engine_credits(%s,%s,%s,%s)",
            (user_id, reservation_id, 71, "settle:integration:001"),
        )
    assert _account(credit_db, user_id) == (130, 0)
    status = credit_db.execute(
        "select status,settled_credits from public.credit_reservations where id=%s",
        (reservation_id,),
    ).fetchone()
    assert status == ("settled", 70)
    assert sorted(row[0] for row in _ledger_types(credit_db, user_id)) == ["grant", "reserve", "settle"]


def test_reservation_rejects_cross_user_run_and_insufficient_balance(credit_db):
    owner, other = str(uuid4()), str(uuid4())
    task_owner, run_owner = str(uuid4()), str(uuid4())
    task_other, run_other = str(uuid4()), str(uuid4())
    _seed_run(credit_db, owner, task_owner, run_owner)
    _seed_run(credit_db, other, task_other, run_other)
    _grant(credit_db, owner, 20, "grant:owner:001")
    with pytest.raises(Exception, match="engine_credit_run_not_reservable"):
        _reserve(credit_db, owner, task_other, run_other, "opencode", 10, "reserve:cross:001")
    with pytest.raises(Exception, match="insufficient_engine_credits"):
        _reserve(credit_db, owner, task_owner, run_owner, "opencode", 21, "reserve:short:001")
    assert _account(credit_db, owner) == (20, 0)
    assert credit_db.execute(
        "select count(*) from credit_reservations where user_id=%s", (owner,)
    ).fetchone()[0] == 0


def test_release_and_expiry_refund_only_after_run_is_terminal(credit_db):
    user_id = str(uuid4())
    task_release, run_release = str(uuid4()), str(uuid4())
    task_expire, run_expire = str(uuid4()), str(uuid4())
    _seed_run(credit_db, user_id, task_release, run_release)
    _grant(credit_db, user_id, 60, "grant:release:001")
    reservation_release = _reserve(
        credit_db, user_id, task_release, run_release, "opencode", 40, "reserve:release:001",
    )
    credit_db.execute("update public.engine_runs set status='failed' where id=%s", (run_release,))
    release_args = (user_id, reservation_release, "engine_cancelled", "release:integration:001")
    assert _service_rpc(credit_db, "select public.release_engine_credits(%s,%s,%s,%s)", release_args)
    assert _service_rpc(credit_db, "select public.release_engine_credits(%s,%s,%s,%s)", release_args)

    _seed_run(credit_db, user_id, task_expire, run_expire)
    reservation_expire = _reserve(
        credit_db, user_id, task_expire, run_expire, "opencode", 20, "reserve:expire:001",
    )
    credit_db.execute(
        "update public.credit_reservations set expires_at=now()-interval '3 hours' where id=%s",
        (reservation_expire,),
    )
    expiry_query = "select public.release_expired_engine_credit_reservations(%s)"
    assert _service_rpc(credit_db, expiry_query, (10,)) == 0
    credit_db.execute("update public.engine_runs set status='failed' where id=%s", (run_expire,))
    assert _service_rpc(credit_db, expiry_query, (10,)) == 1
    assert _account(credit_db, user_id) == (60, 0)
    assert sorted(row[0] for row in _ledger_types(credit_db, user_id)) == ["expire", "grant", "release", "reserve", "reserve"]


def test_concurrent_reservations_cannot_overdraw_available_credits(credit_db, credit_test_dsn):
    import psycopg

    user_id = str(uuid4())
    task_ids, run_ids = (str(uuid4()), str(uuid4())), (str(uuid4()), str(uuid4()))
    _seed_run(credit_db, user_id, task_ids[0], run_ids[0])
    _seed_run(credit_db, user_id, task_ids[1], run_ids[1])
    _grant(credit_db, user_id, 100, "grant:race:001")

    def attempt(index):
        connection = psycopg.connect(credit_test_dsn)
        try:
            with connection.transaction():
                reservation = connection.execute(
                    "select public.reserve_engine_credits(%s,%s,%s,%s,%s,%s)",
                    (user_id, task_ids[index], run_ids[index], "opencode", 70, f"reserve:race:00{index+1}"),
                ).fetchone()[0]
            return ("reserved", str(reservation))
        except Exception as exc:
            if "insufficient_engine_credits" in str(exc):
                return ("insufficient", None)
            raise
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, (0, 1)))
    assert sorted(result[0] for result in results) == ["insufficient", "reserved"]
    assert _account(credit_db, user_id) == (30, 70)
    assert credit_db.execute(
        "select count(*) from credit_reservations where user_id=%s", (user_id,)
    ).fetchone()[0] == 1


def test_authenticated_rls_reads_only_own_rows_and_cannot_write_or_grant(credit_db):
    user_id, other = str(uuid4()), str(uuid4())
    task_id, run_id = str(uuid4()), str(uuid4())
    _seed_run(credit_db, user_id, task_id, run_id)
    credit_db.execute("insert into auth.users (id) values (%s)", (other,))
    _grant(credit_db, user_id, 25, "grant:rls:001")
    _grant(credit_db, other, 75, "grant:rls:002")
    reservation_id = _reserve(
        credit_db, user_id, task_id, run_id, "opencode", 10, "reserve:rls:001",
    )
    credit_db.execute("update public.engine_runs set status='succeeded' where id=%s", (run_id,)
    )
    _service_rpc(
        credit_db, "select public.settle_engine_credits(%s,%s,%s,%s)",
        (user_id, reservation_id, 5, "settle:rls:001"),
    )
    with credit_db.transaction():
        credit_db.execute("set local role authenticated")
        credit_db.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
        visible_accounts = credit_db.execute(
            "select user_id,available_credits from public.credit_accounts order by user_id"
        ).fetchall()
        visible_reservations = credit_db.execute(
            "select user_id,status from public.credit_reservations"
        ).fetchall()
        visible_ledger = credit_db.execute(
            "select user_id,transaction_type from public.credit_ledger order by created_at"
        ).fetchall()
        assert [(str(row[0]), row[1]) for row in visible_accounts] == [(user_id, 20)]
        assert [(str(row[0]), row[1]) for row in visible_reservations] == [(user_id, "settled")]
        assert [str(row[0]) for row in visible_ledger] == [user_id, user_id, user_id]
        assert sorted(row[1] for row in visible_ledger) == ["grant", "reserve", "settle"]

    with pytest.raises(Exception, match="permission denied|row-level security"):
        with credit_db.transaction():
            credit_db.execute("set local role authenticated")
            credit_db.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            credit_db.execute(
                "insert into public.credit_ledger(user_id,transaction_type,available_delta,reserved_delta,idempotency_key) "
                "values (%s,'grant',1,0,'direct-write:001')",
                (user_id,),
            )

    with pytest.raises(Exception, match="permission denied for function"):
        with credit_db.transaction():
            credit_db.execute("set local role authenticated")
            credit_db.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            credit_db.execute(
                "select public.grant_engine_credits(%s,1,'direct','grant:rpc:001')",
                (user_id,),
            )
