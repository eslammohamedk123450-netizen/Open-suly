from __future__ import annotations

from collections import Counter
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "supabase" / "migrations"
_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
_SINGLE_DOLLAR_BODY = re.compile(r"(?m)^as \$(?!\$)|^\$;\s*$")


def test_all_migration_dollar_quote_tags_are_balanced():
    files = sorted(MIGRATIONS.glob("*.sql"))
    assert files, "Supabase migrations must exist"
    for path in files:
        source = path.read_text(encoding="utf-8")
        counts = Counter(_DOLLAR_TAG.findall(source))
        unbalanced = {tag: count for tag, count in counts.items() if count % 2}
        assert not unbalanced, f"{path.name} has unbalanced dollar quote tags: {unbalanced}"
        assert not _SINGLE_DOLLAR_BODY.search(source), (
            f"{path.name} contains a malformed single-dollar PL/pgSQL body delimiter"
        )


def test_migration_version_prefixes_are_unique_and_ordered():
    files = sorted(MIGRATIONS.glob("*.sql"))
    versions = [path.name.split("_", 1)[0] for path in files]
    assert len(versions) == len(set(versions)), "migration version prefixes must be unique"
    assert versions == sorted(versions), "migration filenames must be ordered by version"



def test_engine_credit_ledger_is_owner_readable_and_server_written():
    source = (MIGRATIONS / "20261122111632_credit_ledger_foundation.sql").read_text(encoding="utf-8")
    for table in ("credit_accounts", "credit_reservations", "credit_ledger"):
        assert f"alter table public.{table} enable row level security" in source
        assert f"for select to authenticated using ((select auth.uid()) = user_id)" in source
    assert "available_credits bigint not null default 0" in source
    assert "grant select on public.credit_accounts, public.credit_reservations, public.credit_ledger" in source
    assert "from public, anon, authenticated, service_role" in source
    assert "grant execute on function public.reserve_engine_credits" in source
    assert "grant execute on function public.settle_engine_credits" in source
    assert "grant execute on function public.release_engine_credits" in source
    assert "grant execute on function public.release_expired_engine_credit_reservations" in source
    assert "grant insert" not in source.lower()
    assert "grant update" not in source.lower()
    assert "grant delete" not in source.lower()


def test_expired_credit_holds_are_not_released_while_engine_run_is_running():
    source = (MIGRATIONS / "20261122111632_credit_ledger_foundation.sql").read_text(encoding="utf-8")
    expiry_function = source.split(
        "create or replace function public.release_expired_engine_credit_reservations", 1
    )[1]
    assert "not exists (" in expiry_function
    assert "er.status = 'running'" in expiry_function
    assert "for update skip locked" in expiry_function
    assert "limit p_batch_size" in expiry_function



def test_engine_credit_idempotency_metadata_comparisons_are_null_safe():
    """تمنع NULL في JSON metadata من تجاوز فحص إعادة استخدام مفتاح الرصيد."""
    source = (MIGRATIONS / "20261122111632_credit_ledger_foundation.sql").read_text(encoding="utf-8")
    assert "v_existing.metadata ->> 'reason' is distinct from p_reason" in source
    assert "v_existing.metadata ->> 'actual_credits' is distinct from p_actual_credits::text" in source
    assert not re.search(
        r"v_existing\.metadata\s*->>\s*'[^']+'\s*(?:<>|!=)\s*",
        source,
    )
