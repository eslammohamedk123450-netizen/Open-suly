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
