"""HTTPS adapter for an isolated runtime provisioner.

The provisioner is a separate trusted service. This API process never receives
Docker socket access and never launches host containers directly.
"""
from __future__ import annotations

import json
import re
from time import time
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.services.runtime_broker_contract import RuntimeLease

_ENGINE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_MAX_BODY = 16_384


class RuntimeProvisionerError(RuntimeError):
    pass


class HTTPSRuntimeLeaseProvider:
    """Acquire/release one task-attempt runtime through a pinned HTTPS origin."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        allowed_origins: frozenset[str],
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        origin = f"{parsed.scheme}://{parsed.hostname}" + (
            f":{parsed.port}" if parsed.port else ""
        )
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or origin not in allowed_origins
        ):
            raise ValueError("runtime_provisioner_origin_invalid")
        if not isinstance(bearer_token, str) or not 32 <= len(bearer_token) <= 4096:
            raise ValueError("runtime_provisioner_credential_invalid")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 30:
            raise ValueError("runtime_provisioner_timeout_invalid")
        self._origin = origin
        self._client = httpx.Client(
            base_url=origin,
            headers={"Authorization": f"Bearer {bearer_token}", "Accept": "application/json"},
            timeout=httpx.Timeout(float(timeout_seconds), connect=5.0),
            follow_redirects=False,
            trust_env=False,
            verify=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _json(self, response: httpx.Response, statuses: frozenset[int]) -> dict[str, Any]:
        if 300 <= response.status_code < 400 or response.status_code not in statuses:
            raise RuntimeProvisionerError("runtime_provisioner_unavailable")
        if len(response.content) > _MAX_BODY:
            raise RuntimeProvisionerError("runtime_provisioner_response_too_large")
        if response.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise RuntimeProvisionerError("runtime_provisioner_invalid_content_type")
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeProvisionerError("runtime_provisioner_invalid_response") from exc
        if not isinstance(value, dict):
            raise RuntimeProvisionerError("runtime_provisioner_invalid_response")
        return value

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str) -> RuntimeLease:
        try:
            task, run = UUID(task_id), UUID(engine_run_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("runtime_attempt_identity_invalid") from exc
        if str(task) != task_id or str(run) != engine_run_id or not isinstance(engine_id, str) or not _ENGINE.fullmatch(engine_id):
            raise ValueError("runtime_attempt_identity_invalid")
        try:
            response = self._client.post(
                "/v1/runtimes",
                json={"task_id": task_id, "engine_run_id": engine_run_id, "engine_id": engine_id},
            )
            data = self._json(response, frozenset({201}))
        except httpx.HTTPError as exc:
            raise RuntimeProvisionerError("runtime_provisioner_unreachable") from exc
        try:
            lease = RuntimeLease(
                runtime_id=str(data["runtime_id"]),
                task_id=str(data["task_id"]),
                engine_run_id=str(data["engine_run_id"]),
                engine_id=str(data["engine_id"]),
                base_url=str(data["base_url"]),
                access_token=str(data["access_token"]),
                expires_at=float(data["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeProvisionerError("runtime_provisioner_invalid_lease") from exc
        # Expiry is checked again by TaskScopedRuntimeBroker against the approved origin.
        if lease.expires_at <= time():
            raise RuntimeProvisionerError("runtime_provisioner_expired_lease")
        return lease

    def release(self, lease: RuntimeLease) -> bool:
        if not isinstance(lease, RuntimeLease):
            raise ValueError("runtime_lease_required")
        try:
            runtime_id = str(UUID(lease.runtime_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("runtime_id_invalid") from exc
        if runtime_id != lease.runtime_id:
            raise ValueError("runtime_id_invalid")
        try:
            response = self._client.delete(
                f"/v1/runtimes/{runtime_id}",
                json={"task_id": lease.task_id, "engine_run_id": lease.engine_run_id},
            )
            data = self._json(response, frozenset({200}))
        except httpx.HTTPError as exc:
            raise RuntimeProvisionerError("runtime_provisioner_unreachable") from exc
        if not isinstance(data.get("released"), bool):
            raise RuntimeProvisionerError("runtime_provisioner_invalid_release_response")
        return data["released"]
