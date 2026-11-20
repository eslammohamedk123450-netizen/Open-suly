"""Task-attempt-scoped runtime lease contract for isolated external engines.

This module does not launch containers or create runtimes. It validates the
identity and lifetime of a lease issued by a separately isolated runtime broker.
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

logger = logging.getLogger('suly.runtime_broker')
_ENGINE_ID = re.compile(r'^[a-z][a-z0-9-]{1,62}$')


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
        allowed_hosts: frozenset[str],
        now: float | None = None,
    ) -> None:
        """Validate broker identity, secret shape, URL shape, and short expiry."""
        try:
            runtime_uuid = UUID(self.runtime_id)
            task_uuid = UUID(self.task_id)
            run_uuid = UUID(self.engine_run_id)
            expected_task = UUID(task_id)
            expected_run = UUID(engine_run_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError('invalid_runtime_lease_identity') from exc
        if str(runtime_uuid) != self.runtime_id or str(task_uuid) != self.task_id or str(run_uuid) != self.engine_run_id:
            raise ValueError('runtime_lease_ids_must_be_canonical_uuids')
        if self.task_id != str(expected_task) or self.engine_run_id != str(expected_run):
            raise ValueError('runtime_lease_task_attempt_mismatch')
        if not isinstance(self.engine_id, str) or not _ENGINE_ID.fullmatch(self.engine_id) or self.engine_id != engine_id:
            raise ValueError('runtime_lease_engine_mismatch')
        if not isinstance(self.access_token, str) or len(self.access_token) < 32 or not self.access_token.isascii():
            raise ValueError('runtime_lease_credential_invalid')
        parsed = urlsplit(self.base_url) if isinstance(self.base_url, str) else None
        if (
            parsed is None
            or parsed.scheme not in {'http', 'https'}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {'', '/'}
            or not isinstance(allowed_hosts, frozenset)
            or not allowed_hosts
            or parsed.hostname.lower().rstrip('.') not in allowed_hosts
        ):
            raise ValueError('runtime_lease_base_url_invalid')
        try:
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError('runtime_lease_base_url_invalid')
        except ValueError as exc:
            raise ValueError('runtime_lease_base_url_invalid') from exc
        host = parsed.hostname.lower().rstrip('.')
        if not allowed_hosts or not any(
            host == allowed or host.endswith('.' + allowed)
            for allowed in allowed_hosts
        ):
            raise ValueError('runtime_lease_host_not_allowlisted')
        current = time() if now is None else now
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, (int, float)) or not current < self.expires_at <= current + 3600:
            raise ValueError('runtime_lease_expiry_invalid')


class RuntimeLeaseProvider(Protocol):
    """External broker contract; implementation must provision a fresh runtime per attempt."""

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str) -> RuntimeLease:
        ...

    def release(self, lease: RuntimeLease) -> bool:
        ...


class TaskScopedRuntimeBroker:
    """Validate leases and prevent runtime reuse within this broker process."""

    def __init__(self, provider: RuntimeLeaseProvider, *, allowed_hosts: frozenset[str]) -> None:
        if not callable(getattr(provider, 'acquire', None)) or not callable(getattr(provider, 'release', None)):
            raise TypeError('runtime_lease_provider_required')
        if (
            not isinstance(allowed_hosts, frozenset)
            or not allowed_hosts
            or any(not isinstance(host, str) or not host or host != host.lower() for host in allowed_hosts)
        ):
            raise ValueError('runtime_broker_host_allowlist_required')
        self._provider = provider
        self._allowed_hosts = allowed_hosts
        self._lock = RLock()
        self._active_by_runtime: dict[str, tuple[str, str, str]] = {}
        self._active_by_attempt: dict[tuple[str, str, str], str] = {}
        self._seen_runtime_ids: set[str] = set()
        self._seen_attempts: set[tuple[str, str, str]] = set()

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str) -> RuntimeLease:
        attempt = (task_id, engine_run_id, engine_id)
        with self._lock:
            if attempt in self._seen_attempts:
                raise RuntimeError('runtime_attempt_already_leased')
        lease = self._provider.acquire(task_id, engine_run_id, engine_id)
        if not isinstance(lease, RuntimeLease):
            raise RuntimeError('runtime_provider_returned_invalid_lease')
        try:
            lease.validate(
                task_id=task_id,
                engine_run_id=engine_run_id,
                engine_id=engine_id,
                allowed_hosts=self._allowed_hosts,
            )
        except Exception:
            try:
                self._provider.release(lease)
            except Exception:
                logger.warning('Failed to release invalid runtime lease %s', getattr(lease, 'runtime_id', 'unknown'))
            raise
        with self._lock:
            reused = lease.runtime_id in self._seen_runtime_ids or attempt in self._seen_attempts
            if not reused:
                self._active_by_runtime[lease.runtime_id] = attempt
                self._active_by_attempt[attempt] = lease.runtime_id
                self._seen_runtime_ids.add(lease.runtime_id)
                self._seen_attempts.add(attempt)
        if reused:
            try:
                self._provider.release(lease)
            except Exception:
                logger.warning('Failed to release reused runtime lease %s', lease.runtime_id)
            raise RuntimeError('runtime_instance_reuse_rejected')
        return lease

    def release(self, lease: RuntimeLease) -> bool:
        if not isinstance(lease, RuntimeLease):
            raise ValueError('runtime_lease_required')
        attempt = (lease.task_id, lease.engine_run_id, lease.engine_id)
        with self._lock:
            if self._active_by_runtime.get(lease.runtime_id) != attempt:
                return False
        released = self._provider.release(lease)
        if not isinstance(released, bool):
            raise RuntimeError('runtime_provider_release_invalid_response')
        if released:
            with self._lock:
                if self._active_by_runtime.get(lease.runtime_id) == attempt:
                    self._active_by_runtime.pop(lease.runtime_id, None)
                    self._active_by_attempt.pop(attempt, None)
        return released

    @contextmanager
    def session(self, task_id: str, engine_run_id: str, engine_id: str) -> Iterator[RuntimeLease]:
        """Acquire one runtime lease and always attempt teardown after the engine call."""
        lease = self.acquire(task_id, engine_run_id, engine_id)
        try:
            yield lease
        finally:
            try:
                if not self.release(lease):
                    logger.warning('Runtime teardown was not confirmed for runtime %s', lease.runtime_id)
            except Exception:
                logger.warning('Runtime teardown failed for runtime %s', lease.runtime_id)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_by_runtime)