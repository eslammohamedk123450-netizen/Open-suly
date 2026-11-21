"""SULY-owned trust and approval boundary for Hermes skills.

Skill bytes are stored as inert UTF-8 content. They are never interpreted or
executed by this module; callers may mount only digest-verified, owner-approved
packages into the matching isolated Hermes task runtime.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from supabase import Client

_ALLOWED_LICENSES = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"})
_SKILL_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_MAX_SKILL_BYTES = 256 * 1024


def validate_skill_package(*, name: str, content: bytes, source_revision: str, license_id: str) -> dict[str, Any]:
    """Validate immutable provenance and preserve the exact bytes as UTF-8 text."""
    if not isinstance(name, str) or not _SKILL_NAME.fullmatch(name):
        raise ValueError("hermes_skill_name_invalid")
    if not isinstance(content, bytes) or not 1 <= len(content) <= _MAX_SKILL_BYTES:
        raise ValueError("hermes_skill_content_size_invalid")
    if not isinstance(source_revision, str) or not _REVISION.fullmatch(source_revision):
        raise ValueError("hermes_skill_revision_invalid")
    if not isinstance(license_id, str) or license_id not in _ALLOWED_LICENSES:
        raise ValueError("hermes_skill_license_not_approved")
    try:
        content_utf8 = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("hermes_skill_content_must_be_utf8") from exc
    return {
        "name": name,
        "source_revision": source_revision,
        "license_id": license_id,
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content_bytes": len(content),
        "content_utf8": content_utf8,
        "status": "pending",
        "enabled": False,
    }


class HermesSkillApprovalStore:
    """Server-side persistence; activation always requires owner approval."""

    def __init__(self, client: Client) -> None:
        self._client = client

    @staticmethod
    def _owner(user_id: str) -> str:
        try:
            parsed = UUID(user_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("hermes_skill_owner_invalid") from exc
        if str(parsed) != user_id:
            raise ValueError("hermes_skill_owner_invalid")
        return user_id

    @staticmethod
    def _validate_package(package: dict[str, Any]) -> dict[str, Any]:
        required = {"name", "source_revision", "license_id", "content_sha256", "content_bytes", "content_utf8"}
        if not isinstance(package, dict) or set(package) != required:
            raise ValueError("hermes_skill_package_invalid")
        name, revision, license_id = package["name"], package["source_revision"], package["license_id"]
        content, size, digest = package["content_utf8"], package["content_bytes"], package["content_sha256"]
        if not isinstance(name, str) or not _SKILL_NAME.fullmatch(name):
            raise ValueError("hermes_skill_name_invalid")
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            raise ValueError("hermes_skill_revision_invalid")
        if not isinstance(license_id, str) or license_id not in _ALLOWED_LICENSES:
            raise ValueError("hermes_skill_license_not_approved")
        if not isinstance(content, str):
            raise ValueError("hermes_skill_content_invalid")
        encoded = content.encode("utf-8")
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= _MAX_SKILL_BYTES or len(encoded) != size:
            raise ValueError("hermes_skill_content_size_invalid")
        if not isinstance(digest, str) or not _SHA.fullmatch(digest) or hashlib.sha256(encoded).hexdigest() != digest:
            raise ValueError("hermes_skill_digest_mismatch")
        return package

    def register_candidate(self, *, user_id: str, package: dict[str, Any]) -> dict[str, Any]:
        owner = self._owner(user_id)
        package = self._validate_package(package)
        rows = self._client.table("hermes_skill_approvals").upsert({
            "user_id": owner,
            "name": package["name"],
            "source_revision": package["source_revision"],
            "license_id": package["license_id"],
            "content_sha256": package["content_sha256"],
            "content_bytes": package["content_bytes"],
            "content_utf8": package["content_utf8"],
            "status": "pending",
            "enabled": False,
            "approved_by": None,
            "approved_at": None,
        }, on_conflict="user_id,name,content_sha256").execute().data
        if not rows or not isinstance(rows[0], dict):
            raise RuntimeError("hermes_skill_candidate_persistence_failed")
        return self._projection(rows[0])

    def approve(self, *, user_id: str, skill_id: str, expected_sha256: str) -> dict[str, Any]:
        owner = self._owner(user_id)
        try:
            UUID(skill_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("hermes_skill_id_invalid") from exc
        if not isinstance(expected_sha256, str) or not _SHA.fullmatch(expected_sha256):
            raise ValueError("hermes_skill_digest_invalid")
        rows = self._client.table("hermes_skill_approvals").update({
            "status": "approved", "enabled": True, "approved_by": owner,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", skill_id).eq("user_id", owner).eq(
            "content_sha256", expected_sha256
        ).eq("status", "pending").eq("enabled", False).execute().data
        if not rows or not isinstance(rows[0], dict):
            raise RuntimeError("hermes_skill_approval_conflict")
        return self._projection(rows[0])

    def revoke(self, *, user_id: str, skill_id: str) -> bool:
        owner = self._owner(user_id)
        try:
            UUID(skill_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("hermes_skill_id_invalid") from exc
        rows = self._client.table("hermes_skill_approvals").update({
            "status": "revoked", "enabled": False,
        }).eq("id", skill_id).eq("user_id", owner).eq("enabled", True).execute().data
        return bool(rows)

    def active(self, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        owner = self._owner(user_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("hermes_skill_limit_invalid")
        rows = self._client.table("hermes_skill_approvals").select(
            "id,name,source_revision,license_id,content_sha256,content_bytes,status,enabled,approved_at"
        ).eq("user_id", owner).eq("status", "approved").eq(
            "enabled", True
        ).order("approved_at", desc=True).limit(limit).execute().data
        return [self._projection(row) for row in (rows or []) if isinstance(row, dict)]

    def active_packages(self, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return approved package bytes only after rechecking their exact digest."""
        owner = self._owner(user_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("hermes_skill_limit_invalid")
        rows = self._client.table("hermes_skill_approvals").select(
            "id,name,source_revision,license_id,content_sha256,content_bytes,content_utf8,status,enabled,approved_at"
        ).eq("user_id", owner).eq("status", "approved").eq(
            "enabled", True
        ).order("approved_at", desc=True).limit(limit).execute().data or []
        packages: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("content_utf8"), str):
                continue
            content = row["content_utf8"].encode("utf-8")
            if (
                len(content) != row.get("content_bytes")
                or len(content) > _MAX_SKILL_BYTES
                or hashlib.sha256(content).hexdigest() != row.get("content_sha256")
            ):
                raise RuntimeError("hermes_skill_stored_content_integrity_failure")
            packages.append({**self._projection(row), "content_utf8": row["content_utf8"]})
        return packages

    @staticmethod
    def _projection(row: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "id", "name", "source_revision", "license_id", "content_sha256",
            "content_bytes", "status", "enabled", "approved_at",
        )
        return {key: row.get(key) for key in fields}
