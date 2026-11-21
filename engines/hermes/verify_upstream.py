#!/usr/bin/env python3
"""Fail-closed verification for the pinned original Hermes Agent checkout."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "engines" / "hermes" / "upstream"
EXPECTED_COMMIT = "2de9f51b8008a7d49a49221c184f2f11cbfc4af1"


def fail(message: str) -> None:
    print(f"Hermes source verification failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=UPSTREAM, text=True, stderr=subprocess.STDOUT
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"git command unavailable or failed: {exc}")


def main() -> None:
    marker = UPSTREAM / ".git"
    if not marker.exists() and not marker.is_file():
        fail("submodule is not initialized; checkout with submodules: recursive")

    actual = git("rev-parse", "HEAD")
    if actual != EXPECTED_COMMIT:
        fail(f"unexpected upstream commit {actual}")
    if git("status", "--porcelain"):
        fail("upstream checkout has local modifications")

    for relative in ("LICENSE", "Dockerfile", "pyproject.toml"):
        if not (UPSTREAM / relative).is_file():
            fail(f"required upstream source file is missing: {relative}")

    dockerfile = (UPSTREAM / "Dockerfile").read_text(encoding="utf-8")
    required_runtime_contract = (
        "ENV HERMES_HOME=/opt/data",
        'ENTRYPOINT [ "/opt/hermes/docker/entrypoint-dispatch.sh" ]',
        "ENV HERMES_PYTHON=/opt/hermes/.venv/bin/python",
    )
    for marker in required_runtime_contract:
        if marker not in dockerfile:
            fail(f"upstream Dockerfile runtime contract changed: {marker}")

    print(
        "Hermes source verified: "
        f"commit={actual} license=present "
        "home=/opt/data entrypoint=upstream-dispatcher"
    )


if __name__ == "__main__":
    main()
