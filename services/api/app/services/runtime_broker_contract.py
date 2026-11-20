"""Task-attempt-scoped runtime lease contract for isolated external engines.

This module validates leases from an external provisioner. It never launches
containers, routes arbitrary user URLs, or claims cross-process isolation.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import ipaddress
import logging
import re
from threading import RLock
from time import time
from typing import Iterator, Protocol
from urllib.parse import urlsplit
from uuid import UUID

logger = logging.getLogger("suly.runtime_broker")
_ENGINE_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_TOKEN = re.compile(r"^[A-Za-z0-9._~+/-]{32,4096}={0,2}$")
_DNS_HOST = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r"(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
)


def _normalized_origin(parsed) -> str:
    host = parsed.hostname.lower().rstrip(".")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme.lower()}://{host}{port}"


def _valid_https_origin(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
        port = parsed.port
        ipaddress.ip_address(host)
    except (TypeError, ValueError, AttributeError):
        # DNS names are expected; malformed URLs and IP literals are rejected below.
        try:
            parsed = urlsplit(value)
            host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
            port = parsed.port
        except (TypeError, ValueError, AttributeError):
            return False
    else:
        return False
    if (
        parsed.scheme != "https"
        or not _DNS_HOST.fullmatch(host)
        or host == "localhost"
        or host.endswith(".localhost")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (port is not None and not 1 <= port <= 65535)
    ):
        return False
    return value == _normalized_origin(parsed)


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
    gateway_path: str = ""

    def validate(
        self,
        *,
        task_id: str,
        engine_run_id: str,
        engine_id: str,
        allowed_origins: frozenset[str],
        now: float | None = None,
    ) -> None:
        """Validate canonical identity, exact HTTPS origin, secret shape, and expiry."""
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
        if not isinstance(self.access_token, str) or not _TOKEN.fullmatch(self.access_token):
            raise ValueError("runtime_lease_credential_invalid")

        try:
            parsed = urlsplit(self.base_url)
            normalized_origin = _normalized_origin(parsed) if parsed.hostname else ""
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("runtime_lease_base_url_invalid") from exc

        gateway_path_valid = (
            self.gateway_path == ""
            or self.gateway_path == f"/v1/runtime-gateway/{self.runtime_id}"
        )
        if (
            not gateway_path_valid
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not isinstance(allowed_origins, frozenset)
            or not allowed_origins
            or not _valid_https_origin(normalized_origin)
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
    """Provider must enforce fresh runtime identity globally across workers."""

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str, *, files: list[dict] | None = None) -> RuntimeLease:
        ...

    def run_task(
        self, lease: RuntimeLease, *, prompt: str, title: str = "SULY task",
        on_session_created: Callable[[RuntimeLease, str], None] | None = None,
    ) -> dict:
        ...

    def recover(self, runtime_id: str, task_id: str, engine_run_id: str, engine_id: str = "opencode") -> RuntimeLease:
        ...

    def release(self, lease: RuntimeLease) -> bool:
        ...


class TaskScopedRuntimeBroker:
    """Validate task-attempt leases and guard runtime reuse within this process.

    The external provider remains responsible for global uniqueness, process-tree
    teardown, credential revocation, and cleanup after worker/process crashes.
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
            or any(not _valid_https_origin(origin) for origin in allowed_origins)
        ):
            raise ValueError("runtime_broker_allowed_origins_required")

        self._provider = provider
        self._allowed_origins = allowed_origins
        self._lock = RLock()
        self._active_by_runtime: dict[str, tuple[tuple[str, str, str], RuntimeLease]] = {}
        self._active_by_attempt: dict[tuple[str, str, str], str] = {}
        self._seen_runtime_ids: set[str] = set()
        self._seen_attempts: set[tuple[str, str, str]] = set()
        self._pending_attempts: set[tuple[str, str, str]] = set()
        self._releasing_runtime_ids: set[str] = set()

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str, *, files: list[dict] | None = None) -> RuntimeLease:
        if files is not None and (not isinstance(files, list) or len(files) > 200):
            raise ValueError("runtime_workspace_snapshot_invalid")
        attempt = (task_id, engine_run_id, engine_id)
        with self._lock:
            if attempt in self._seen_attempts or attempt in self._pending_attempts:
                raise RuntimeError("runtime_attempt_already_leased")
            self._pending_attempts.add(attempt)

        try:
            if files is None:
                lease = self._provider.acquire(task_id, engine_run_id, engine_id)
            else:
                lease = self._provider.acquire(task_id, engine_run_id, engine_id, files=files)
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
                runtime_id = getattr(lease, "runtime_id", None)
                with self._lock:
                    runtime_was_seen = isinstance(runtime_id, str) and runtime_id in self._seen_runtime_ids
                if not runtime_was_seen:
                    try:
                        self._provider.release(lease)
                    except Exception:
                        logger.warning(
                            "Failed to release invalid runtime lease %s",
                            runtime_id if isinstance(runtime_id, str) else "unknown",
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
                if not runtime_reused:
                    try:
                        if not self._provider.release(lease):
                            logger.warning(
                                "Could not release duplicate-attempt runtime %s",
                                lease.runtime_id,
                            )
                    except Exception:
                        logger.warning(
                            "Failed to release duplicate-attempt runtime %s",
                            lease.runtime_id,
                        )
                else:
                    # Never tear down an ID that may still belong to another task.
                    logger.error(
                        "Runtime provider reused runtime identity %s; refusing unsafe teardown",
                        lease.runtime_id,
                    )
                raise RuntimeError("runtime_instance_reuse_rejected")
            return lease
        finally:
            with self._lock:
                self._pending_attempts.discard(attempt)

    def run_task(
        self,
        task_id: str,
        engine_run_id: str,
        engine_id: str,
        *,
        files: list[dict] | None,
        prompt: str,
        title: str = "SULY task",
        on_lease_acquired: Callable[[RuntimeLease], None] | None = None,
        on_session_created: Callable[[RuntimeLease, str], None] | None = None,
    ) -> dict:
        """Execute and retain the lease for approvals/review until explicit release.

        Failed executions are torn down immediately. Successful runtimes remain
        task-scoped and expire at the provisioner TTL if the API worker crashes.
        """
        runner = getattr(self._provider, "run_task", None)
        if not callable(runner):
            raise RuntimeError("runtime_provider_execution_not_supported")
        if on_lease_acquired is not None and not callable(on_lease_acquired):
            raise ValueError("runtime_lease_callback_invalid")
        lease = self.acquire(task_id, engine_run_id, engine_id, files=files)
        try:
            if on_lease_acquired is not None:
                on_lease_acquired(lease)
            if on_session_created is not None and not callable(on_session_created):
                raise ValueError("runtime_session_callback_invalid")
            result = runner(
                lease, prompt=prompt, title=title,
                on_session_created=on_session_created,
            )
            if not isinstance(result, dict):
                raise RuntimeError("runtime_provider_invalid_execution_result")
            safe_result = dict(result)
            execution = safe_result.get("execution")
            if isinstance(execution, dict):
                execution = dict(execution)
                execution["runtime_id"] = lease.runtime_id
                safe_result["execution"] = execution
            return safe_result
        except Exception:
            try:
                self.release(lease)
            except Exception:
                logger.warning("Runtime teardown failed after task error %s", lease.runtime_id)
            raise

    def recover(
        self,
        runtime_id: str,
        task_id: str,
        engine_run_id: str,
        engine_id: str = "opencode",
    ) -> RuntimeLease:
        """Rebuild an active lease after process restart using owner-bound rotation."""
        attempt = (task_id, engine_run_id, engine_id)
        with self._lock:
            active_id = self._active_by_attempt.get(attempt)
            active = self._active_by_runtime.get(active_id) if active_id else None
            if active is not None and active[0] == attempt:
                return active[1]
            if attempt in self._seen_attempts or attempt in self._pending_attempts:
                raise RuntimeError("runtime_attempt_recovery_rejected")
            self._pending_attempts.add(attempt)
        try:
            recoverer = getattr(self._provider, "recover", None)
            if not callable(recoverer):
                raise RuntimeError("runtime_provider_recovery_not_supported")
            lease = recoverer(runtime_id, task_id, engine_run_id, engine_id)
            if not isinstance(lease, RuntimeLease):
                raise RuntimeError("runtime_provider_returned_invalid_lease")
            lease.validate(
                task_id=task_id,
                engine_run_id=engine_run_id,
                engine_id=engine_id,
                allowed_origins=self._allowed_origins,
            )
            with self._lock:
                if lease.runtime_id in self._seen_runtime_ids or attempt in self._seen_attempts:
                    raise RuntimeError("runtime_instance_reuse_rejected")
                self._active_by_runtime[lease.runtime_id] = (attempt, lease)
                self._active_by_attempt[attempt] = lease.runtime_id
                self._seen_runtime_ids.add(lease.runtime_id)
                self._seen_attempts.add(attempt)
            return lease
        finally:
            with self._lock:
                self._pending_attempts.discard(attempt)

    def lease_for_attempt(
        self, task_id: str, engine_run_id: str, engine_id: str
    ) -> RuntimeLease | None:
        attempt = (task_id, engine_run_id, engine_id)
        with self._lock:
            runtime_id = self._active_by_attempt.get(attempt)
            active = self._active_by_runtime.get(runtime_id) if runtime_id else None
            return active[1] if active and active[0] == attempt else None

    def release_attempt(self, task_id: str, engine_run_id: str, engine_id: str) -> bool:
        lease = self.lease_for_attempt(task_id, engine_run_id, engine_id)
        return self.release(lease) if lease is not None else False

    def release(self, lease: RuntimeLease) -> bool:
        if not isinstance(lease, RuntimeLease):
            raise ValueError("runtime_lease_required")
        attempt = (lease.task_id, lease.engine_run_id, lease.engine_id)
        with self._lock:
            active = self._active_by_runtime.get(lease.runtime_id)
            if (
                active is None
                or active[0] != attempt
                or active[1] is not lease
                or lease.runtime_id in self._releasing_runtime_ids
            ):
                return False
            self._releasing_runtime_ids.add(lease.runtime_id)

        try:
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
        finally:
            with self._lock:
                self._releasing_runtime_ids.discard(lease.runtime_id)

    @contextmanager
    def session(
        self,
        task_id: str,
        engine_run_id: str,
        engine_id: str,
        *,
        files: list[dict] | None = None,
    ) -> Iterator[RuntimeLease]:
        """Acquire one runtime lease and always attempt teardown after engine use."""
        lease = self.acquire(task_id, engine_run_id, engine_id, files=files)
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
