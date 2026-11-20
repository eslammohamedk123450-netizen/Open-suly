"""Task-attempt-scoped runtime lease contract for isolated external engines.

This module validates leases from an external provisioner. It never launches
containers, routes arbitrary user URLs, or claims cross-process isolation.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
import re
from threading import RLock
from time import time
from typing import Iterator, Protocol
from urllib.parse import urlsplit
from uuid import UUID

logger = logging.getLogger("suly.runtime_broker")
_ENGINE_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_ORIGIN = re.compile(r"^https?://[a-z0-9.-]+(?::[1-9][0-9]{0,4})?$")


def _normalized_origin(parsed) -> str:
    host = parsed.hostname.lower().rstrip(".")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme.lower()}://{host}{port}"


@dataclass(frozen=True)
class RuntimeLease:
    """Opaque access lease for exactly one task attempt and one engine."""

    runtime_id: str
    task_id: str
    engine_run_id: str
    engine_id: str
    base_url: str
    access_token: str = field(repr=False)
    expires_at: float

    def validate(
        self,
        *,
        task_id: str,
        engine_run_id: str,
        engine_id: str,
        allowed_origins: frozenset[str],
        now: float | None = None,
    ) -> None:
        """Validate canonical identity, endpoint origin, secret shape, and expiry."""
        try:
            runtime_uuid = UUID(self.runtime_id)
            task_uuid = UUID(self.task_id)
            run_uuid = UUID(self.engine_run_id)
            expected_task = UUID(task_id)
            expected_run = UUID(engine_run_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("invalid_runtime_lease_identity") from exc

        if (
            str(runtime_uuid) != self.runtime_id
            or str(task_uuid) != self.task_id
            or str(run_uuid) != self.engine_run_id
        ):
            raise ValueError("runtime_lease_ids_must_be_canonical_uuids")
        if self.task_id != str(expected_task) or self.engine_run_id != str(expected_run):
            raise ValueError("runtime_lease_task_attempt_mismatch")
        if (
            not isinstance(self.engine_id, str)
            or not _ENGINE_ID.fullmatch(self.engine_id)
            or self.engine_id != engine_id
        ):
            raise ValueError("runtime_lease_engine_mismatch")
        if (
            not isinstance(self.access_token, str)
            or len(self.access_token) < 32
            or not self.access_token.isascii()
        ):
            raise ValueError("runtime_lease_credential_invalid")

        try:
            parsed = urlsplit(self.base_url)
            normalized_origin = _normalized_origin(parsed) if parsed.hostname else ""
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("runtime_lease_base_url_invalid") from exc

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not isinstance(allowed_origins, frozenset)
            or not allowed_origins
            or normalized_origin not in allowed_origins
        ):
            raise ValueError("runtime_lease_base_url_invalid")

        current = time() if now is None else now
        if (
            isinstance(self.expires_at, bool)
            or not isinstance(self.expires_at, (int, float))
            or not current < self.expires_at <= current + 3600
        ):
            raise ValueError("runtime_lease_expiry_invalid")


class RuntimeLeaseProvider(Protocol):
    """Provider must provision a fresh runtime globally for every task attempt."""

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str) -> RuntimeLease:
        ...

    def release(self, lease: RuntimeLease) -> bool:
        ...


class TaskScopedRuntimeBroker:
    """Validate leases and prevent reuse within this broker process.

    The provider must also enforce uniqueness across workers/processes and must
    terminate the process tree, revoke credentials, and remove task state.
    """

    def __init__(
        self,
        provider: RuntimeLeaseProvider,
        *,
        allowed_origins: frozenset[str],
    ) -> None:
        if (
            not callable(getattr(provider, "acquire", None))
            or not callable(getattr(provider, "release", None))
        ):
            raise TypeError("runtime_lease_provider_required")
        if (
            not isinstance(allowed_origins, frozenset)
            or not allowed_origins
            or any(
                not isinstance(origin, str) or not _ORIGIN.fullmatch(origin)
                for origin in allowed_origins
            )
        ):
            raise ValueError("runtime_broker_allowed_origins_required")

        self._provider = provider
        self._allowed_origins = allowed_origins
        self._lock = RLock()
        self._active_by_runtime: dict[str, tuple[tuple[str, str, str], RuntimeLease]] = {}
        self._active_by_attempt: dict[tuple[str, str, str], str] = {}
        self._seen_runtime_ids: set[str] = set()
        self._seen_attempts: set[tuple[str, str, str]] = set()

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str) -> RuntimeLease:
        attempt = (task_id, engine_run_id, engine_id)
        with self._lock:
            if attempt in self._seen_attempts:
                raise RuntimeError("runtime_attempt_already_leased")

        lease = self._provider.acquire(task_id, engine_run_id, engine_id)
        if not isinstance(lease, RuntimeLease):
            raise RuntimeError("runtime_provider_returned_invalid_lease")
        try:
            lease.validate(
                task_id=task_id,
                engine_run_id=engine_run_id,
                engine_id=engine_id,
                allowed_origins=self._allowed_origins,
            )
        except Exception:
            try:
                self._provider.release(lease)
            except Exception:
                logger.warning(
                    "Failed to release invalid runtime lease %s",
                    getattr(lease, "runtime_id", "unknown"),
                )
            raise

        with self._lock:
            runtime_reused = lease.runtime_id in self._seen_runtime_ids
            attempt_reused = attempt in self._seen_attempts
            reused = runtime_reused or attempt_reused
            if not reused:
                self._active_by_runtime[lease.runtime_id] = (attempt, lease)
                self._active_by_attempt[attempt] = lease.runtime_id
                self._seen_runtime_ids.add(lease.runtime_id)
                self._seen_attempts.add(attempt)

        if reused:
            # Never tear down a runtime ID that has already been issued: it may
            # still belong to another active task or another broker process.
            if not runtime_reused:
                try:
                    if not self._provider.release(lease):
                        logger.warning("Could not release duplicate-attempt runtime %s", lease.runtime_id)
                except Exception:
                    logger.warning("Failed to release duplicate-attempt runtime %s", lease.runtime_id)
            else:
                logger.error("Runtime provider reused runtime identity %s; refusing unsafe teardown", lease.runtime_id)
            raise RuntimeError("runtime_instance_reuse_rejected")
        return lease

    def release(self, lease: RuntimeLease) -> bool:
        if not isinstance(lease, RuntimeLease):
            raise ValueError("runtime_lease_required")
        attempt = (lease.task_id, lease.engine_run_id, lease.engine_id)
        with self._lock:
            active = self._active_by_runtime.get(lease.runtime_id)
            if active is None or active[0] != attempt or active[1] is not lease:
                return False

        released = self._provider.release(lease)
        if not isinstance(released, bool):
            raise RuntimeError("runtime_provider_release_invalid_response")
        if released:
            with self._lock:
                active = self._active_by_runtime.get(lease.runtime_id)
                if active is not None and active[0] == attempt and active[1] is lease:
                    self._active_by_runtime.pop(lease.runtime_id, None)
                    self._active_by_attempt.pop(attempt, None)
        return released

    @contextmanager
    def session(
        self,
        task_id: str,
        engine_run_id: str,
        engine_id: str,
    ) -> Iterator[RuntimeLease]:
        """Acquire one runtime lease and always attempt teardown after engine use."""
        lease = self.acquire(task_id, engine_run_id, engine_id)
        try:
            yield lease
        finally:
            try:
                if not self.release(lease):
                    logger.warning(
                        "Runtime teardown was not confirmed for runtime %s",
                        lease.runtime_id,
                    )
            except Exception:
                logger.warning("Runtime teardown failed for runtime %s", lease.runtime_id)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_by_runtime)
