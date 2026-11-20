"""Lease-aware client for the pinned Hermes native Runs API.

Hermes is a single-tenant runtime. This client remains disabled unless the
deployment explicitly attests that a per-task isolated runtime is in use.
SULY owns authorization, task leases, and the durable upstream run reference.
"""
from __future__ import annotations

import asyncio
import json
import re
from contextlib import suppress
from threading import Event
from typing import Callable
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings


class HermesAgentUnavailable(RuntimeError):
    """Raised when the optional isolated Hermes runtime is not configured."""


class HermesAgentError(RuntimeError):
    """Raised for bounded, non-sensitive upstream failures."""


class HermesAgentCancelled(RuntimeError):
    """Raised after Hermes confirms that an interrupted run is cancelled."""


_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})
_MAX_PROMPT_CHARS = 20_000
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SSE_EVENT_NAMES = frozenset({
    "tool.started", "tool.completed", "subagent.start", "subagent.complete",
    "run.queued", "run.completed", "run.failed", "run.cancelled",
    "run.interrupted", "run.stopping", "run.steered",
    "approval.request", "approval.responded",
})


def _safe_run_event(payload: object, expected_run_id: str) -> dict[str, str | int | float] | None:
    """Return metadata-only progress; never forward previews, prompts, or tool output."""
    if not isinstance(payload, dict) or payload.get("run_id") != expected_run_id:
        return None
    name = payload.get("event")
    if not isinstance(name, str) or name not in _SSE_EVENT_NAMES:
        return None
    summary: dict[str, str | int | float] = {"event": name}
    seq = payload.get("seq")
    if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
        summary["seq"] = seq
    timestamp = payload.get("timestamp")
    if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
        summary["timestamp"] = float(timestamp)
    return summary


async def _consume_run_events(
    client: httpx.AsyncClient,
    base_url: str,
    run_id: str,
    headers: dict[str, str],
    callback: Callable[[dict[str, str | int | float]], None],
) -> None:
    """Consume Hermes SSE as a best-effort metadata-only progress channel."""
    try:
        async with client.stream(
            "GET",
            f"{base_url}/v1/runs/{run_id}/events",
            headers=headers,
            timeout=httpx.Timeout(30.0, connect=5.0),
        ) as response:
            response.raise_for_status()
            data_lines: list[str] = []
            async for line in response.aiter_lines():
                if len(line) > 65_536:
                    data_lines.clear()
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].strip())
                elif line == "" and data_lines:
                    try:
                        payload = json.loads("\n".join(data_lines))
                        summary = _safe_run_event(payload, run_id)
                        if summary is not None:
                            try:
                                await asyncio.to_thread(callback, summary)
                            except Exception:
                                # Progress delivery must never change task execution outcome.
                                pass
                    except (ValueError, TypeError):
                        pass
                    data_lines.clear()
    except (httpx.HTTPError, ValueError, TypeError):
        # Status polling remains authoritative if the optional event stream is unavailable.
        return


def _validate_base_url(value: str) -> str:
    # نمنع بيانات الدخول أو query string داخل عنوان الخادم.
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise HermesAgentUnavailable("Hermes agent base URL is invalid.")
    return value.rstrip("/")


def run_agent_turn(
    prompt: str,
    *,
    timeout_seconds: float | None = None,
    cancel_event: Event | None = None,
    idempotency_key: str | None = None,
    on_run_started: Callable[[str], bool] | None = None,
    on_event: Callable[[dict[str, str | int | float]], None] | None = None,
) -> dict[str, str]:
    """Create and poll one durable Hermes run; stop it when SULY signals cancellation.

    The callback must persist the opaque upstream run ID using the active SULY
    step lease. A failed persistence check immediately requests upstream stop.
    """
    settings = get_settings()
    if not settings.hermes_agent_enabled:
        raise HermesAgentUnavailable("Hermes agent runtime is disabled.")
    if not settings.hermes_agent_isolation_confirmed:
        raise HermesAgentUnavailable("Hermes per-task isolation is not confirmed.")
    if not settings.hermes_agent_base_url or not settings.hermes_agent_api_key:
        raise HermesAgentUnavailable("Hermes agent runtime is not configured.")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > _MAX_PROMPT_CHARS:
        raise ValueError("Hermes prompt must contain 1–20000 characters.")
    if (
        not isinstance(idempotency_key, str)
        or not 1 <= len(idempotency_key) <= 255
        or not idempotency_key.isascii()
        or any(ord(ch) < 33 or ord(ch) > 126 for ch in idempotency_key)
    ):
        raise ValueError("Hermes idempotency key must contain 1–255 visible ASCII characters.")
    if on_run_started is None:
        raise ValueError("Hermes upstream run persistence callback is required.")

    base_url = _validate_base_url(settings.hermes_agent_base_url)
    token = settings.hermes_agent_api_key.get_secret_value()
    timeout = timeout_seconds if timeout_seconds is not None else settings.hermes_agent_timeout_seconds
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 1 <= timeout <= 300
    ):
        raise ValueError("Hermes request timeout is outside the allowed range.")
    if cancel_event is not None and cancel_event.is_set():
        raise HermesAgentCancelled("Hermes request was cancelled.")

    async def request() -> dict[str, str]:
        # كل طلب HTTP له مهلة قصيرة حتى يظل فحص الإلغاء واستعادة الـlease ممكنين.
        per_request_timeout = httpx.Timeout(15.0, connect=5.0)
        headers = {"Authorization": f"Bearer {token}"}
        deadline = asyncio.get_running_loop().time() + timeout
        run_id: str | None = None
        event_task: asyncio.Task | None = None

        async with httpx.AsyncClient(timeout=per_request_timeout) as client:
            try:
                # نطلب من Hermes إنشاء تشغيل دائم بمفتاح idempotency ثابت للمحاولة.
                response = await client.post(
                    f"{base_url}/v1/runs",
                    headers={**headers, "Idempotency-Key": idempotency_key},
                    json={"input": prompt.strip()},
                )
                response.raise_for_status()
                admission = response.json()
                run_id = admission.get("run_id") if isinstance(admission, dict) else None
                if not isinstance(run_id, str) or not _RUN_ID_PATTERN.fullmatch(run_id):
                    raise HermesAgentError("Hermes returned an invalid run identifier.")

                # لا نكمل التنفيذ قبل حفظ المعرف الخارجي داخل سجل المحاولة في SULY.
                # إذا فشل RPC بسبب انقطاع مؤقت، نعيد محاولة الحفظ idempotently قبل إيقاف التشغيل.
                try:
                    persisted = on_run_started(run_id)
                except Exception:
                    try:
                        persisted = on_run_started(run_id)
                    except Exception:
                        persisted = False
                if not persisted:
                    try:
                        stop_response = await client.post(
                            f"{base_url}/v1/runs/{run_id}/stop",
                            headers=headers,
                        )
                        stop_response.raise_for_status()
                    except httpx.HTTPError:
                        # سجل stop_pending (إن تم حفظه متأخرًا) سيعيد محاولة الإيقاف من reconciler.
                        pass
                    raise HermesAgentError("SULY could not persist the Hermes run reference.")

                # Events are supplementary; the status endpoint remains authoritative.
                if on_event is not None:
                    event_task = asyncio.create_task(
                        _consume_run_events(client, base_url, run_id, headers, on_event)
                    )

                while True:
                    # عند الإلغاء نطلب الإيقاف من Hermes ثم ننتظر الحالة النهائية بحد زمني.
                    if cancel_event is not None and cancel_event.is_set():
                        stop_response = await client.post(
                            f"{base_url}/v1/runs/{run_id}/stop",
                            headers=headers,
                        )
                        stop_response.raise_for_status()
                        stop_deadline = min(deadline + 30.0, asyncio.get_running_loop().time() + 30.0)
                        while asyncio.get_running_loop().time() < stop_deadline:
                            status_response = await client.get(
                                f"{base_url}/v1/runs/{run_id}",
                                headers=headers,
                            )
                            status_response.raise_for_status()
                            status_payload = status_response.json()
                            if not isinstance(status_payload, dict):
                                raise HermesAgentError("Hermes returned an invalid run status.")
                            status = status_payload.get("status")
                            if status in _TERMINAL_STATUSES:
                                if status == "cancelled":
                                    raise HermesAgentCancelled("Hermes run was cancelled.")
                                if status == "completed":
                                    break
                                raise HermesAgentError("Hermes run ended after cancellation was requested.")
                            await asyncio.sleep(0.5)
                        else:
                            raise HermesAgentError("Hermes stop request did not settle within the safety timeout.")
                        if status == "completed":
                            content = status_payload.get("output")
                            if isinstance(content, str) and content.strip():
                                return {"engine": "hermes-agent", "content": content[:settings.hermes_agent_max_output_chars]}
                            raise HermesAgentError("Hermes returned an invalid completed run.")

                    # نوقف الانتظار قبل تجاوز المهلة الكلية للمهمة.
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        try:
                            await client.post(f"{base_url}/v1/runs/{run_id}/stop", headers=headers)
                        except httpx.HTTPError:
                            pass
                        raise HermesAgentError("Hermes run exceeded its configured timeout.")

                    status_response = await client.get(
                        f"{base_url}/v1/runs/{run_id}",
                        headers=headers,
                    )
                    status_response.raise_for_status()
                    status_payload = status_response.json()
                    if not isinstance(status_payload, dict):
                        raise HermesAgentError("Hermes returned an invalid run status.")
                    status = status_payload.get("status")
                    if status == "completed":
                        output = status_payload.get("output")
                        if not isinstance(output, str) or not output.strip():
                            raise HermesAgentError("Hermes returned an empty run output.")
                        if len(output) > settings.hermes_agent_max_output_chars:
                            raise HermesAgentError("Hermes run output exceeded the configured limit.")
                        return {"engine": "hermes-agent", "content": output}
                    if status in {"failed", "interrupted", "unknown"}:
                        raise HermesAgentError("Hermes run did not complete successfully.")
                    if status == "cancelled":
                        raise HermesAgentCancelled("Hermes run was cancelled.")
                    if status not in {"started", "running", "stopping"}:
                        raise HermesAgentError("Hermes returned an unknown run status.")
                    await asyncio.sleep(min(0.5, max(0.05, remaining)))

            except HermesAgentCancelled:
                raise
            except HermesAgentError:
                raise
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                # لا نمرر جسم الاستجابة أو نص الخطأ الخارجي لأنه قد يحتوي على أسرار.
                raise HermesAgentError("Hermes run request failed.") from exc
            finally:
                if event_task is not None:
                    event_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await event_task

    return asyncio.run(request())


def stop_agent_run(upstream_run_id: str, *, timeout_seconds: float = 30.0) -> bool:
    """Request upstream stop and confirm a terminal state without reading output.

    لا تعتبر استجابة طلب الإيقاف وحدها دليلاً على توقف المحرك؛ ننتظر حالة
    نهائية مؤكدة، وإلا نعيد خطأ آمنًا كي يعيد reconciler المحاولة لاحقًا.
    """
    settings = get_settings()
    # إيقاف تشغيل معروف لا يبدأ runtime جديدًا؛ يجب أن يظل متاحًا حتى بعد تعطيل المحرك.
    if not settings.hermes_agent_base_url or not settings.hermes_agent_api_key:
        raise HermesAgentUnavailable("Hermes agent runtime is not configured.")
    if not isinstance(upstream_run_id, str) or not _RUN_ID_PATTERN.fullmatch(upstream_run_id):
        raise ValueError("Hermes upstream run identifier is invalid.")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not 1 <= timeout_seconds <= 60
    ):
        raise ValueError("Hermes stop timeout is outside the allowed range.")

    base_url = _validate_base_url(settings.hermes_agent_base_url)
    token = settings.hermes_agent_api_key.get_secret_value()

    async def stop_and_confirm() -> bool:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            try:
                response = await client.post(
                    f"{base_url}/v1/runs/{upstream_run_id}/stop",
                    headers=headers,
                )
                response.raise_for_status()
                while asyncio.get_running_loop().time() < deadline:
                    status_response = await client.get(
                        f"{base_url}/v1/runs/{upstream_run_id}",
                        headers=headers,
                    )
                    status_response.raise_for_status()
                    payload = status_response.json()
                    if not isinstance(payload, dict):
                        raise HermesAgentError("Hermes returned an invalid run status.")
                    status = payload.get("status")
                    if status in _TERMINAL_STATUSES:
                        return True
                    if status not in {"started", "running", "stopping"}:
                        raise HermesAgentError("Hermes returned an unknown run status.")
                    await asyncio.sleep(min(0.5, max(0.05, deadline - asyncio.get_running_loop().time())))
                return False
            except HermesAgentError:
                raise
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise HermesAgentError("Hermes stop reconciliation failed.") from exc

    return asyncio.run(stop_and_confirm())



def steer_agent_run(
    upstream_run_id: str,
    steer_text: str,
    *,
    timeout_seconds: float = 15.0,
) -> bool:
    """Send bounded user guidance to one existing Hermes run; never starts a new run."""
    settings = get_settings()
    if not settings.hermes_agent_enabled or not settings.hermes_agent_isolation_confirmed:
        raise HermesAgentUnavailable("Hermes steering is disabled or isolation is not confirmed.")
    if not settings.hermes_agent_base_url or not settings.hermes_agent_api_key:
        raise HermesAgentUnavailable("Hermes agent runtime is not configured.")
    if not isinstance(upstream_run_id, str) or not _RUN_ID_PATTERN.fullmatch(upstream_run_id):
        raise ValueError("Hermes upstream run identifier is invalid.")
    if not isinstance(steer_text, str) or not steer_text.strip() or len(steer_text) > _MAX_PROMPT_CHARS:
        raise ValueError("Hermes steer input must contain 1–20000 characters.")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not 1 <= timeout_seconds <= 30
    ):
        raise ValueError("Hermes steer timeout is outside the allowed range.")

    base_url = _validate_base_url(settings.hermes_agent_base_url)
    token = settings.hermes_agent_api_key.get_secret_value()

    async def send_steer() -> bool:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0)
        ) as client:
            try:
                response = await client.post(
                    f"{base_url}/v1/runs/{upstream_run_id}/steer",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"input": steer_text.strip()},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise HermesAgentError("Hermes returned an invalid steer response.")
                response_run_id = payload.get("run_id")
                if response_run_id is not None and response_run_id != upstream_run_id:
                    raise HermesAgentError("Hermes steer response run identifier did not match.")
                if payload.get("accepted") is not True:
                    raise HermesAgentError("Hermes did not accept the steer input.")
                return True
            except HermesAgentError:
                raise
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise HermesAgentError("Hermes steer request failed.") from exc

    return asyncio.run(send_steer())
