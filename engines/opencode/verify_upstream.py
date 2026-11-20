#!/usr/bin/env python3
"""Fail-closed verification for the pinned OpenCode source checkout."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engines" / "opencode"
UPSTREAM = ENGINE / "upstream"
EXPECTED_COMMIT = "4cca18d80450a3dd6a9a4142028bde84ccb3116e"
EXPECTED_VERSION = "2.3.0"
EXPECTED_BUN = "bun@1.4.4"


def fail(message: str) -> None:
    print(f"OpenCode source verification failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=UPSTREAM, text=True, stderr=subprocess.STDOUT
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"git command unavailable or failed: {exc}")


def main() -> None:
    if not (UPSTREAM / ".git").exists() and not (UPSTREAM / ".git").is_file():
        fail("submodule is not initialized; checkout with submodules: recursive")

    actual_commit = git("rev-parse", "HEAD")
    if actual_commit != EXPECTED_COMMIT:
        fail(f"unexpected upstream commit {actual_commit}")

    if git("status", "--porcelain"):
        fail("upstream checkout has local modifications")

    manifest = json.loads((UPSTREAM / "package.json").read_text(encoding="utf-8"))
    if manifest.get("version") != EXPECTED_VERSION:
        fail("root package version does not match the audited version")
    if manifest.get("packageManager") != EXPECTED_BUN:
        fail("package manager pin does not match the audited Bun version")
    if manifest.get("license") != "MIT":
        fail("upstream root license changed; repeat license review")

    server_manifest = json.loads(
        (UPSTREAM / "packages" / "server" / "package.json").read_text(encoding="utf-8")
    )
    if server_manifest.get("name") != "@opencode/server":
        fail("expected upstream server workspace package is missing")
    if server_manifest.get("version") != EXPECTED_VERSION:
        fail("server package version does not match the audited version")
    if not (UPSTREAM / "LICENSE").is_file():
        fail("upstream LICENSE file is missing")
    if not (UPSTREAM / "bun.lock").is_file() and not (UPSTREAM / "bun.lockb").is_file():
        fail("upstream Bun lockfile is missing")

    print(
        "OpenCode source verified: "
        f"commit={actual_commit} version={EXPECTED_VERSION} "
        f"server=@opencode/server license=MIT"
    )


if __name__ == "__main__":
    main()
