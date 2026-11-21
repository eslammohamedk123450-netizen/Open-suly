"""Private SULY runtime API for isolated OpenCode and Hermes task runtimes.

Deploy behind TLS on a dedicated worker host. This service alone owns Docker access.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import hmac
import json
import os
import re
import sqlite3
import tarfile
import tempfile
import time
from threading import Lock
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.docker_runtime import DockerTaskRuntimeManager, RuntimeErrorSafe, validate_egress_disabled

DATABASE = os.environ.get("RUNTIME_DB_PATH", "/var/lib/suly-runtime/runtimes.sqlite3")
SULY_TOKEN = os.environ.get("SULY_PROVISIONER_TOKEN", "")
PUBLIC_GATEWAY_ORIGIN = os.environ.get("RUNTIME_GATEWAY_ORIGIN", "")
IMAGE = os.environ.get("OPENCODE_RUNTIME_IMAGE", "")
HERMES_IMAGE = os.environ.get("HERMES_RUNTIME_IMAGE", "")
WORKSPACE_ROOT = os.environ.get("RUNTIME_WORKSPACE_ROOT", "/var/lib/suly-runtime/workspaces")
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_RESULT_FILES = 500
MAX_RUNTIME_CREATE_BODY_BYTES = 6 * 1024 * 1024
_ID = re.compile(r"^[0-9a-f-]{36}$")
_ALLOWED_PROXY = {
    ("GET", "/api/event"), ("GET", "/api/info"), ("POST", "/api/session"),
    ("GET", "/api/skill"), ("GET", "/api/provider"),
}
_HERMES_RUNTIME_PROFILE = "suly-hermes-task-v1"
_HERMES_RUN_ID = r"[A-Za-z0-9_-]{1,128}"
_HERMES_ALLOWED_ROUTES = {
    ("GET", "/health"),
    ("GET", "/v1/capabilities"),
    ("GET", "/v1/models"),
    ("GET", "/v1/skills"),
    ("GET", "/v1/toolsets"),
    ("POST", "/v1/runs"),
}

def _allowed_opencode_route(method: str, route: str) -> bool:
    if (method, route) in _ALLOWED_PROXY:
        return True
    patterns = (
        ("GET", r"/api/session/ses[A-Za-z0-9_-]{1,128}/permission"),
        ("POST", r"/api/session/ses[A-Za-z0-9_-]{1,128}/permission/per[A-Za-z0-9_-]{1,128}/reply"),
        ("POST", r"/api/session/ses[A-Za-z0-9_-]{1,128}/prompt"),
        ("POST", r"/api/session/ses[A-Za-z0-9_-]{1,128}/interrupt"),
    )
    return any(method == expected and re.fullmatch(pattern, route) for method, pattern in patterns)


def _allowed_hermes_route(method: str, route: str) -> bool:
    """Allow only SULY-required Hermes routes; never expose generic upstream APIs."""
    if (method, route) in _HERMES_ALLOWED_ROUTES:
        return True
    patterns = (
        ("GET", rf"/v1/runs/{_HERMES_RUN_ID}"),
        ("GET", rf"/v1/runs/{_HERMES_RUN_ID}/events"),
        ("POST", rf"/v1/runs/{_HERMES_RUN_ID}/stop"),
        ("POST", rf"/v1/runs/{_HERMES_RUN_ID}/steer"),
        ("POST", rf"/v1/runs/{_HERMES_RUN_ID}/approval"),
    )
    return any(method == expected and re.fullmatch(pattern, route) for expected, pattern in patterns)
logger = logging.getLogger("suly.runtime_provisioner")
_cleanup_task: asyncio.Task | None = None

app = FastAPI(title="SULY Runtime Provisioner", docs_url=None, redoc_url=None, openapi_url=None)
_runtime_managers: dict[str, DockerTaskRuntimeManager] = {}
_runtime_manager_lock = Lock()


class FileSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=262144)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CreateRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    engine_run_id: str
    engine_id: str = "opencode"
    runtime_profile: str | None = None
    files: list[FileSnapshot] = Field(default_factory=list, max_length=200)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=32000)
    session_id: str | None = Field(default=None, pattern=r"^ses[A-Za-z0-9_-]{1,128}$")
    title: str = Field(default="SULY task", min_length=1, max_length=120)


class RecoverRuntime(BaseModel):
    task_id: str
    engine_run_id: str


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE), mode=0o700, exist_ok=True)
    db = sqlite3.connect(DATABASE, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS runtimes (
        runtime_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, engine_run_id TEXT NOT NULL,
        engine_id TEXT NOT NULL, container_id TEXT NOT NULL, host_port INTEGER NOT NULL,
        token_hash TEXT NOT NULL, expires_at REAL NOT NULL, created_at REAL NOT NULL,
        baseline_json TEXT NOT NULL DEFAULT '{}'
    )""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(runtimes)")}
    if "baseline_json" not in columns:
        db.execute("ALTER TABLE runtimes ADD COLUMN baseline_json TEXT NOT NULL DEFAULT '{}'")
    if "runtime_profile" not in columns:
        db.execute("ALTER TABLE runtimes ADD COLUMN runtime_profile TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS idx_runtime_expiry ON runtimes(expires_at)")
    return db


def _wait_for_opencode(host_port: int, token: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    with httpx.Client(
        base_url=f"http://127.0.0.1:{host_port}",
        auth=("opencode", token),
        timeout=httpx.Timeout(2.0, connect=1.0),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get("/api/info")
                if response.status_code == 200 and response.headers.get("content-type", "").split(";", 1)[0].lower() == "application/json":
                    payload = response.json()
                    if isinstance(payload, dict) and (
                        isinstance(payload.get("version"), str)
                        or isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("version"), str)
                    ):
                        return
            except (httpx.HTTPError, ValueError, AttributeError):
                pass
            time.sleep(0.5)
    raise RuntimeErrorSafe("opencode_startup_timeout")

def _wait_for_hermes(host_port: int, token: str, timeout_seconds: float = 45.0) -> None:
    """Wait for the pinned upstream Hermes API server, not merely an open TCP port."""
    deadline = time.monotonic() + timeout_seconds
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    with httpx.Client(
        base_url=f"http://127.0.0.1:{host_port}",
        headers=headers,
        timeout=httpx.Timeout(2.0, connect=1.0),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get("/v1/capabilities")
                if response.status_code == 200 and response.headers.get("content-type", "").split(";", 1)[0].lower() == "application/json":
                    payload = response.json()
                    if isinstance(payload, dict) and payload:
                        return
            except (httpx.HTTPError, ValueError, AttributeError):
                pass
            time.sleep(0.5)
    raise RuntimeErrorSafe("hermes_startup_timeout")

def _get_manager(engine_id: str = "opencode") -> DockerTaskRuntimeManager:
    """Return a lazy per-engine manager; Hermes and OpenCode have different immutable images."""
    if engine_id not in {"opencode", "hermes-agent"}:
        raise ValueError("runtime_engine_not_allowed")
    image = IMAGE if engine_id == "opencode" else HERMES_IMAGE
    env_name = "OPENCODE_RUNTIME_IMAGE" if engine_id == "opencode" else "HERMES_RUNTIME_IMAGE"
    if not image or not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", image):
        raise RuntimeError(f"{env_name} must be digest-pinned")
    with _runtime_manager_lock:
        manager = _runtime_managers.get(engine_id)
        if manager is None:
            manager = DockerTaskRuntimeManager(image=image, workspace_root=WORKSPACE_ROOT)
            _runtime_managers[engine_id] = manager
        return manager


def _require_suly(authorization: str | None) -> None:
    if not SULY_TOKEN:
        raise HTTPException(503, "provisioner_auth_not_configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "unauthorized")
    supplied = authorization[7:]
    if not hmac.compare_digest(supplied, SULY_TOKEN):
        raise HTTPException(401, "unauthorized")


def _identity(value: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(422, "invalid_identity") from exc
    if str(parsed) != value:
        raise HTTPException(422, "invalid_identity")
    return value


def _derive_runtime_access_token(runtime_id: str, task_id: str, run_id: str) -> str:
    """Derive a stable per-runtime credential without storing plaintext secrets."""
    if not SULY_TOKEN:
        raise RuntimeError("runtime_credential_derivation_unavailable")
    message = f"suly-runtime-v1:{runtime_id}:{task_id}:{run_id}".encode("utf-8")
    return hmac.new(SULY_TOKEN.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _runtime(runtime_id: str, token: str | None):
    if not _ID.fullmatch(runtime_id) or not token or len(token) > 256:
        raise HTTPException(404, "runtime_not_found")
    with _db() as db:
        row = db.execute("SELECT * FROM runtimes WHERE runtime_id=?", (runtime_id,)).fetchone()
    if row is None or row["expires_at"] <= time.time():
        raise HTTPException(404, "runtime_not_found")
    digest = hashlib.sha256(token.encode()).hexdigest()
    if not hmac.compare_digest(digest, row["token_hash"]):
        raise HTTPException(404, "runtime_not_found")
    return row


async def _cleanup_expired_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_get_manager().cleanup_expired)
            db = _db()
            try:
                db.execute("DELETE FROM runtimes WHERE expires_at<=?", (time.time(),))
                db.commit()
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Do not log container env, access tokens, or user workspace contents.
            logger.exception("runtime_cleanup_failed")
        await asyncio.sleep(30)


@app.on_event("startup")
async def startup() -> None:
    global _cleanup_task
    # Reject unsafe or misspelled egress settings before starting cleanup or
    # accepting runtime requests. Docker networks remain internal in all cases.
    validate_egress_disabled()
    if not SULY_TOKEN:
        raise RuntimeError("SULY_PROVISIONER_TOKEN is required")
    if not IMAGE or not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", IMAGE):
        raise RuntimeError("OPENCODE_RUNTIME_IMAGE must be digest-pinned")
    parsed = httpx.URL(PUBLIC_GATEWAY_ORIGIN)
    if (parsed.scheme != "https" or not parsed.host or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise RuntimeError("RUNTIME_GATEWAY_ORIGIN must be an HTTPS origin without path or credentials")
    db = _db()
    db.close()
    _cleanup_task = asyncio.create_task(_cleanup_expired_loop(), name="suly-runtime-cleanup")


@app.on_event("shutdown")
async def shutdown() -> None:
    global _cleanup_task
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None


@app.post("/v1/runtimes", status_code=201)
async def create_runtime(request: Request, authorization: str | None = Header(default=None)):
    _require_suly(authorization)
    raw_body = await _read_bounded_request_body(request, limit=MAX_RUNTIME_CREATE_BODY_BYTES)
    try:
        body = CreateRuntime.model_validate(json.loads(raw_body))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "invalid_runtime_request") from exc
    task_id, run_id = _identity(body.task_id), _identity(body.engine_run_id)
    if body.engine_id != "opencode":
        raise HTTPException(422, "engine_not_allowed")
    if body.engine_id not in {"opencode", "hermes-agent"}:
        raise HTTPException(422, "engine_not_allowed")
    if body.engine_id == "hermes-agent" and body.runtime_profile != _HERMES_RUNTIME_PROFILE:
        raise HTTPException(422, "runtime_profile_required")
    if body.engine_id == "opencode" and body.runtime_profile is not None:
        raise HTTPException(422, "runtime_profile_not_applicable")
    try:
        manager = _get_manager(body.engine_id)
    except RuntimeError as exc:
        raise HTTPException(503, "runtime_image_not_configured") from exc
    try:
        result = manager.create(
            task_id=task_id,
            engine_run_id=run_id,
            engine_id=body.engine_id,
            runtime_profile=body.runtime_profile,
            files=[item.model_dump(exclude_none=True) for item in body.files],
            access_token_factory=_derive_runtime_access_token,
        )
    except (ValueError, RuntimeErrorSafe) as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        if body.engine_id == "hermes-agent":
            _wait_for_hermes(result["host_port"], result["access_token"])
        else:
            _wait_for_opencode(result["host_port"], result["access_token"])
        with _db() as db:
            db.execute(
                "INSERT INTO runtimes (runtime_id,task_id,engine_run_id,engine_id,runtime_profile,container_id,host_port,token_hash,expires_at,created_at,baseline_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (result["runtime_id"], task_id, run_id, body.engine_id,
                 body.runtime_profile, result["container_id"], result["host_port"],
                 hashlib.sha256(result["access_token"].encode()).hexdigest(),
                 result["expires_at"], time.time(),
                 json.dumps({item.path: item.sha256 or hashlib.sha256(item.content.encode()).hexdigest() for item in body.files}, separators=(",", ":"))),
            )
    except Exception as exc:
        manager.destroy(runtime_id=result["runtime_id"], task_id=task_id, engine_run_id=run_id)
        if isinstance(exc, RuntimeErrorSafe):
            raise HTTPException(503, f"{body.engine_id}_startup_failed") from exc
        raise HTTPException(503, "runtime_registration_failed") from exc
    return {
        "runtime_id": result["runtime_id"],
        "task_id": task_id,
        "engine_run_id": run_id,
        "engine_id": body.engine_id,
        "runtime_profile": body.runtime_profile,
        "base_url": PUBLIC_GATEWAY_ORIGIN.rstrip("/"),
        "gateway_path": f"/v1/runtime-gateway/{result['runtime_id']}",
        "access_token": result["access_token"],
        "expires_at": result["expires_at"],
    }


@app.delete("/v1/runtimes/{runtime_id}")
def release_runtime(runtime_id: str, body: dict[str, str], authorization: str | None = Header(default=None)):
    _require_suly(authorization)
    task_id = _identity(body.get("task_id", ""))
    run_id = _identity(body.get("engine_run_id", ""))
    with _db() as db:
        row = db.execute("SELECT * FROM runtimes WHERE runtime_id=?", (runtime_id,)).fetchone()
    if row is None:
        return {"released": False}
    if row["task_id"] != task_id or row["engine_run_id"] != run_id:
        raise HTTPException(404, "runtime_not_found")
    try:
        released = _get_manager(row["engine_id"]).destroy(runtime_id=runtime_id, task_id=task_id, engine_run_id=run_id)
    except (ValueError, RuntimeErrorSafe) as exc:
        raise HTTPException(409, "runtime_release_rejected") from exc
    if released:
        with _db() as db:
            db.execute("DELETE FROM runtimes WHERE runtime_id=?", (runtime_id,))
    return {"released": released}


@app.post("/v1/runtimes/{runtime_id}/recover")
def recover_runtime(
    runtime_id: str,
    body: RecoverRuntime,
    authorization: str | None = Header(default=None),
):
    """Reconstruct the same task-bound credential after an API/worker restart.

    The token is derived with HMAC from the service secret and canonical
    runtime identity; only its SHA-256 digest is persisted in SQLite.
    """
    _require_suly(authorization)
    runtime_id = _identity(runtime_id)
    task_id = _identity(body.task_id)
    run_id = _identity(body.engine_run_id)
    with _db() as db:
        row = db.execute(
            "SELECT task_id,engine_run_id,engine_id,runtime_profile,expires_at,token_hash FROM runtimes WHERE runtime_id=?",
            (runtime_id,),
        ).fetchone()
    if (
        row is None
        or row["task_id"] != task_id
        or row["engine_run_id"] != run_id
        or row["expires_at"] <= time.time()
    ):
        raise HTTPException(404, "runtime_not_found")
    token = _derive_runtime_access_token(runtime_id, task_id, run_id)
    digest = hashlib.sha256(token.encode()).hexdigest()
    if not hmac.compare_digest(digest, row["token_hash"]):
        raise HTTPException(409, "runtime_recovery_credential_mismatch")
    return {
        "runtime_id": runtime_id,
        "task_id": task_id,
        "engine_run_id": run_id,
        "engine_id": row["engine_id"],
        "runtime_profile": row["runtime_profile"],
        "base_url": PUBLIC_GATEWAY_ORIGIN.rstrip("/"),
        "gateway_path": f"/v1/runtime-gateway/{runtime_id}",
        "access_token": token,
        "expires_at": row["expires_at"],
    }


@app.api_route("/v1/runtime-gateway/{runtime_id}/{path:path}", methods=["GET", "POST"])
async def runtime_gateway(runtime_id: str, path: str, request: Request, authorization: str | None = Header(default=None)):
    row = _runtime(runtime_id, authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
    if request.method == "POST" and path == "execute":
        raw_body = await _read_bounded_request_body(request, limit=65536)
        try:
            payload = ExecuteRequest.model_validate(json.loads(raw_body))
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "invalid_execution_request") from exc
        return await execute(runtime_id, payload, authorization)
    route = "/" + path
    method = request.method
    allowed_route = (
        _allowed_hermes_route(method, route)
        if row["engine_id"] == "hermes-agent"
        else _allowed_opencode_route(method, route)
    )
    if not allowed_route:
        raise HTTPException(404, "route_not_allowed")
    body = await _read_bounded_request_body(request, limit=65536)
    headers = {"Accept": request.headers.get("accept", "application/json")}
    if body:
        headers["Content-Type"] = request.headers.get("content-type", "application/json")
    runtime_token = _runtime_token_from_request(authorization)
    upstream_headers = (
        {"Authorization": f"Bearer {runtime_token}"}
        if row["engine_id"] == "hermes-agent"
        else {}
    )
    client = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{row['host_port']}",
        auth=None if row["engine_id"] == "hermes-agent" else ("opencode", runtime_token),
        headers=upstream_headers,
        timeout=httpx.Timeout(300, connect=3, read=240),
        follow_redirects=False, trust_env=False,
    )
    upstream = None
    streaming = False
    try:
        upstream_request = client.build_request(method, route, content=body, headers=headers)
        upstream = await client.send(upstream_request, stream=True)
        if 300 <= upstream.status_code < 400:
            raise HTTPException(502, "upstream_redirect_rejected")
        safe_headers = {}
        for key in ("content-type", "cache-control"):
            if key in upstream.headers:
                safe_headers[key] = upstream.headers[key]

        # OpenCode's event endpoint is an unbounded SSE stream. Buffering it
        # until EOF deadlocks the event consumer and loses real-time updates.
        is_opencode_events = row["engine_id"] == "opencode" and method == "GET" and route == "/api/event"
        is_hermes_events = (
            row["engine_id"] == "hermes-agent"
            and method == "GET"
            and re.fullmatch(rf"/v1/runs/{_HERMES_RUN_ID}/events", route) is not None
        )
        if is_opencode_events or is_hermes_events:
            content_type = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "text/event-stream":
                raise HTTPException(502, "runtime_event_stream_invalid_content_type")
            safe_headers["Cache-Control"] = "no-cache"
            safe_headers["X-Accel-Buffering"] = "no"
            streaming = True

            async def forward_events():
                try:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk
                finally:
                    await upstream.aclose()
                    await client.aclose()

            return StreamingResponse(
                forward_events(),
                status_code=upstream.status_code,
                headers=safe_headers,
            )

        chunks, total = [], 0
        async for chunk in upstream.aiter_bytes():
            total += len(chunk)
            if total > 2 * 1024 * 1024:
                raise HTTPException(502, "upstream_response_too_large")
            chunks.append(chunk)
        return Response(
            b"".join(chunks),
            status_code=upstream.status_code,
            headers=safe_headers,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "runtime_unreachable") from exc
    finally:
        if not streaming:
            if upstream is not None:
                await upstream.aclose()
            await client.aclose()


async def _read_bounded_request_body(request: Request, *, limit: int) -> bytes:
    """Enforce request limits while streaming; never buffer an unbounded body."""
    if not 1 <= limit <= 8 * 1024 * 1024:
        raise ValueError("request_body_limit_invalid")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "invalid_content_length") from exc
        if declared_size < 0:
            raise HTTPException(400, "invalid_content_length")
        if declared_size > limit:
            raise HTTPException(413, "request_too_large")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, "request_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _runtime_token_from_request(value: str | None) -> str:
    return value[7:] if value and value.startswith("Bearer ") else ""


async def _bounded_opencode_json(client: httpx.AsyncClient, path: str, payload: dict[str, Any], *, limit: int) -> dict[str, Any]:
    async with client.stream("POST", path, json=payload) as response:
        if response.status_code < 200 or response.status_code >= 300 or 300 <= response.status_code < 400:
            raise HTTPException(502, "opencode_execution_failed")
        if response.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise HTTPException(502, "opencode_invalid_content_type")
        chunks, total = [], 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > limit:
                raise HTTPException(502, "opencode_response_too_large")
            chunks.append(chunk)
    try:
        value = json.loads(b"".join(chunks))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(502, "opencode_invalid_json") from exc
    if not isinstance(value, dict):
        raise HTTPException(502, "opencode_invalid_response")
    return value


@app.post("/v1/runtime-gateway/{runtime_id}/execute")
async def execute(runtime_id: str, body: ExecuteRequest, authorization: str | None = Header(default=None)):
    row = _runtime(runtime_id, _runtime_token_from_request(authorization))
    base = f"http://127.0.0.1:{row['host_port']}"
    auth = ("opencode", _runtime_token_from_request(authorization))
    try:
        async with httpx.AsyncClient(base_url=base, auth=auth, timeout=httpx.Timeout(900, connect=5), trust_env=False) as client:
            session_id = body.session_id
            if session_id is None:
                payload = await _bounded_opencode_json(client, "/api/session", {
                    "title": body.title,
                    "permissions": [{"action": "*", "resource": "*", "effect": "ask"}],
                }, limit=16_384)
                session_data = payload.get("data")
                session_id = session_data.get("id") if isinstance(session_data, dict) else None
                if not isinstance(session_id, str) or not re.fullmatch(r"ses[A-Za-z0-9_-]{1,128}", session_id):
                    raise HTTPException(502, "invalid_session_response")
            if not re.fullmatch(r"ses[A-Za-z0-9_-]{1,128}", session_id):
                raise HTTPException(422, "invalid_session_id")
            result = await _bounded_opencode_json(
                client, f"/api/session/{session_id}/prompt",
                {"text": body.prompt}, limit=2 * 1024 * 1024,
            )
            return {"runtime_id": runtime_id, "session_id": session_id, "result": result}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, "opencode_execution_failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "opencode_runtime_unreachable") from exc


@app.get("/v1/runtimes/{runtime_id}/results")
def runtime_results(runtime_id: str, authorization: str | None = Header(default=None)):
    row = _runtime(runtime_id, _runtime_token_from_request(authorization))
    try:
        container = _get_manager().client.containers.get(row["container_id"])
        stream, _stat = container.get_archive("/workspace")
        archive_parts, archive_size = [], 0
        for chunk in stream:
            archive_size += len(chunk)
            if archive_size > MAX_RESULT_BYTES + 2 * 1024 * 1024:
                raise HTTPException(413, "result_archive_too_large")
            archive_parts.append(chunk)
        archive = BytesIO(b"".join(archive_parts))
        files, total = [], 0
        baseline = json.loads(row["baseline_json"] or "{}")
        with tarfile.open(fileobj=archive, mode="r:*") as tar:
            members = tar.getmembers()
            if len(members) > MAX_RESULT_FILES + 1:
                raise HTTPException(413, "result_file_limit_exceeded")
            for member in members:
                if member.isdir():
                    continue
                rel = PurePosixPath(member.name)
                if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
                    continue
                parts = rel.parts[1:] if rel.parts and rel.parts[0] == "workspace" else rel.parts
                if not parts or member.issym() or member.islnk() or not member.isfile():
                    continue
                if any(p in {"..", ".git", "node_modules"} or p.lower().startswith(".env") for p in parts):
                    continue
                if member.size > 1024 * 1024:
                    continue
                extracted = tar.extractfile(member)
                if extracted is None:
                    continue
                data = extracted.read(1024 * 1024 + 1)
                total += len(data)
                if total > MAX_RESULT_BYTES:
                    raise HTTPException(413, "result_size_limit_exceeded")
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                files.append({"path": "/".join(parts), "content": text,
                              "sha256": hashlib.sha256(data).hexdigest()})
        current = {item["path"]: item["sha256"] for item in files}
        changed = [item for item in files if baseline.get(item["path"]) != item["sha256"]]
        deleted = sorted(set(baseline) - set(current))
        return {"runtime_id": runtime_id, "file_count": len(files), "changed_count": len(changed),
                "deleted_paths": deleted, "total_bytes": total, "changed_files": changed}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "runtime_results_unavailable") from exc


@app.post("/internal/cleanup")
def cleanup(authorization: str | None = Header(default=None)):
    _require_suly(authorization)
    removed = _get_manager().cleanup_expired()
    with _db() as db:
        db.execute("DELETE FROM runtimes WHERE expires_at<=?", (time.time(),))
    return {"removed": removed}
