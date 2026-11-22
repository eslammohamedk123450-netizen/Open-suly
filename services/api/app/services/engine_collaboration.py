"""Typed, fail-closed collaboration contracts between isolated SULY engines.

Engines never share sessions, memory, credentials, processes, or writable
workspaces. This module validates the only data shapes allowed to cross the
SULY collaboration boundary: task contracts, immutable artifact references,
lifecycle events, and bounded result envelopes.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from uuid import UUID

_ENGINE_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_.-]{1,95}$")
_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$")
_EVENT_TYPES = frozenset({
    "handoff.created", "handoff.approved", "handoff.started",
    "handoff.completed", "handoff.failed", "handoff.cancelled",
    "artifact.published", "review.requested", "review.accepted",
    "review.rejected", "workspace.locked", "workspace.released",
})
_TERMINAL = frozenset({"completed", "failed", "cancelled"})


def _uuid(value: str, field: str) -> None:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"collaboration_{field}_invalid") from exc
    if str(parsed) != value:
        raise ValueError(f"collaboration_{field}_invalid")


def _engine(value: str) -> None:
    if not isinstance(value, str) or not _ENGINE_ID.fullmatch(value):
        raise ValueError("collaboration_engine_id_invalid")


@dataclass(frozen=True)
class ArtifactReference:
    """Opaque immutable pointer; artifact bytes never cross engine control APIs."""

    artifact_id: str
    owner_id: str
    project_id: str | None
    sha256: str
    byte_size: int
    media_type: str

    def validate(self, *, owner_id: str, max_bytes: int = 5 * 1024 * 1024) -> None:
        _uuid(self.owner_id, "artifact_owner")
        if self.owner_id != owner_id:
            raise ValueError("collaboration_artifact_owner_mismatch")
        if not isinstance(self.artifact_id, str) or not _ARTIFACT_ID.fullmatch(self.artifact_id):
            raise ValueError("collaboration_artifact_id_invalid")
        if self.project_id is not None:
            _uuid(self.project_id, "artifact_project")
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise ValueError("collaboration_artifact_digest_invalid")
        if isinstance(self.byte_size, bool) or not isinstance(self.byte_size, int) or not 0 <= self.byte_size <= max_bytes:
            raise ValueError("collaboration_artifact_size_invalid")
        if not isinstance(self.media_type, str) or not _MEDIA_TYPE.fullmatch(self.media_type):
            raise ValueError("collaboration_artifact_media_type_invalid")


@dataclass(frozen=True)
class TaskContract:
    """Bounded engine-to-engine task handoff approved and owned by SULY."""

    task_id: str
    owner_id: str
    parent_run_id: str
    source_engine: str
    target_engine: str
    capability: str
    artifact_refs: tuple[ArtifactReference, ...]
    depth: int = 1
    max_child_tasks: int = 1
    max_parallel_children: int = 1
    max_runtime_seconds: int = 300
    max_input_bytes: int = 64_000
    approval_id: str | None = None

    def validate(self) -> None:
        _uuid(self.task_id, "task_id")
        _uuid(self.owner_id, "owner_id")
        _uuid(self.parent_run_id, "parent_run_id")
        _engine(self.source_engine)
        _engine(self.target_engine)
        if self.source_engine == self.target_engine:
            raise ValueError("collaboration_same_engine_handoff_rejected")
        if not isinstance(self.capability, str) or not _CAPABILITY.fullmatch(self.capability):
            raise ValueError("collaboration_capability_invalid")
        if not isinstance(self.artifact_refs, tuple) or len(self.artifact_refs) > 32:
            raise ValueError("collaboration_artifact_refs_invalid")
        seen: set[str] = set()
        for artifact in self.artifact_refs:
            if not isinstance(artifact, ArtifactReference):
                raise ValueError("collaboration_artifact_ref_required")
            artifact.validate(owner_id=self.owner_id)
            if artifact.artifact_id in seen:
                raise ValueError("collaboration_duplicate_artifact")
            seen.add(artifact.artifact_id)
        bounds = (
            ("depth", self.depth, 1, 3),
            ("max_child_tasks", self.max_child_tasks, 1, 8),
            ("max_parallel_children", self.max_parallel_children, 1, 2),
            ("max_runtime_seconds", self.max_runtime_seconds, 1, 1800),
            ("max_input_bytes", self.max_input_bytes, 1, 64_000),
        )
        for name, value, low, high in bounds:
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"collaboration_{name}_out_of_bounds")
        # Runtime limits are enforced by the selected engine's registry/adapter.
        # The collaboration contract stays engine-agnostic and applies only the
        # shared upper bound above; adding an engine must not require editing
        # this contract.
        if self.max_parallel_children > self.max_child_tasks:
            raise ValueError("collaboration_parallelism_exceeds_child_budget")
        if self.approval_id is not None:
            _uuid(self.approval_id, "approval_id")


@dataclass(frozen=True)
class CollaborationEvent:
    """Metadata-only event; no prompt, free-form output, command, or secret fields."""

    event_id: str
    task_id: str
    owner_id: str
    source_engine: str
    target_engine: str
    event_type: str
    artifact_refs: tuple[str, ...] = ()
    status: str | None = None
    sequence: int | None = None

    def validate(self) -> None:
        _uuid(self.event_id, "event_id")
        _uuid(self.task_id, "task_id")
        _uuid(self.owner_id, "owner_id")
        _engine(self.source_engine)
        _engine(self.target_engine)
        if self.event_type not in _EVENT_TYPES:
            raise ValueError("collaboration_event_type_invalid")
        if self.status is not None and self.status not in {"pending", "approved", "running", *_TERMINAL}:
            raise ValueError("collaboration_event_status_invalid")
        if self.sequence is not None and (
            isinstance(self.sequence, bool) or not isinstance(self.sequence, int)
            or not 0 <= self.sequence <= 1_000_000_000
        ):
            raise ValueError("collaboration_event_sequence_invalid")
        if not isinstance(self.artifact_refs, tuple) or len(self.artifact_refs) > 32:
            raise ValueError("collaboration_event_artifacts_invalid")
        if any(not isinstance(item, str) or not _ARTIFACT_ID.fullmatch(item) for item in self.artifact_refs):
            raise ValueError("collaboration_event_artifacts_invalid")


@dataclass(frozen=True)
class EngineResultEnvelope:
    """A result is accepted only from the expected engine and bounded artifact set."""

    task_id: str
    owner_id: str
    engine_id: str
    status: str
    artifact_refs: tuple[ArtifactReference, ...]
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0

    def validate(self, *, expected_engine: str) -> None:
        _uuid(self.task_id, "result_task_id")
        _uuid(self.owner_id, "result_owner_id")
        _engine(self.engine_id)
        _engine(expected_engine)
        if self.engine_id != expected_engine:
            raise ValueError("collaboration_result_engine_mismatch")
        if self.status not in _TERMINAL:
            raise ValueError("collaboration_result_status_invalid")
        if not isinstance(self.artifact_refs, tuple) or len(self.artifact_refs) > 32:
            raise ValueError("collaboration_result_artifacts_invalid")
        for item in self.artifact_refs:
            item.validate(owner_id=self.owner_id)
        for name, value, maximum in (
            ("input_tokens", self.input_tokens, 10_000_000),
            ("output_tokens", self.output_tokens, 10_000_000),
            ("duration_ms", self.duration_ms, 86_400_000),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
                raise ValueError(f"collaboration_result_{name}_invalid")


def validate_artifact_handoff(
    artifacts: tuple[ArtifactReference, ...], *, owner_id: str,
    target_engine: str, approved_media_types: frozenset[str],
) -> tuple[ArtifactReference, ...]:
    """Intersect references with an explicit per-handoff media-type allowlist."""
    _engine(target_engine)
    if not isinstance(approved_media_types, frozenset) or not approved_media_types:
        raise ValueError("collaboration_media_allowlist_required")
    if not isinstance(artifacts, tuple) or len(artifacts) > 32:
        raise ValueError("collaboration_artifact_refs_invalid")
    accepted = []
    for item in artifacts:
        item.validate(owner_id=owner_id)
        if item.media_type not in approved_media_types:
            raise ValueError("collaboration_artifact_media_type_not_approved")
        accepted.append(item)
    return tuple(accepted)
