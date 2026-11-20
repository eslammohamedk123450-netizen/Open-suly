"""Private SULY runtime API and task-scoped OpenCode gateway.

Deploy behind TLS on a dedicated worker host. This service alone owns Docker access.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import tarfile
import tempfile
import time
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.docker_runtime import DockerTaskRuntimeManager, RuntimeErrorSafe

DATABASE = os.environ.get("RUNTIME_DB_PATH", "/var/lib/suly-runtime/runtimes.sqlite3")
SULY_TOKEN = os.environ.get("SULY_PROVISIONER_TOKEN", "")
PUBLIC_GATEWAY_ORIGIN = os.environ.get("RUNTIME_GATEWAY_ORIGIN", "")
IMAGE = os.environ.get("OPENCODE_RUNTIME_IMAGE", "")
WORKSPACE_ROOT = os.environ.get("RUNTIME_WORKSPACE_ROOT", "/var/lib/suly-runtime/workspaces")
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_RESULT_FILES = 500
_ID = re.compile(r"^[0-9a-f-]{36}$")
_ALLOWED_PROXY = {
    ("GET", "/api/info"), ("POST", "/api/session"),
    ("GET", "/api/skill"), ("GET", "/api/provider"),
}
app = FastAPI(title="SULY Runtime Provisioner", docs_url=None, redoc_url=None, openapi_url=None)
_manager: DockerTaskRuntimeManager | None = None


class FileSnapshot(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=262144)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CreateRuntime(BaseModel):
    task_id: str
    engine_run_id: str
    engine_id: str = "opencode"
    files: list[FileSnapshot] = Field(default_factory=list, max_length=200)


class ExecuteRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32000)
    session_id: str | None = Field(default=None, pattern=r"^ses[A-Za-z0-9_-]{1,128}$")
    title: str = Field(default="SULY task", min_length=1, max_length=120)


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
    db.execute("CREATE INDEX IF NOT EXISTS idx_runtime_expiry ON runtimes(expires_at)")
    return db


def _manager() -> DockerTaskRuntimeManager:
    global _manager
    if _manager is None:
        if not IMAGE or "@sha256:" not in IMAGE:
            raise RuntimeError("OPENCODE_RUNTIME_IMAGE must be digest-pinned")
        _manager = DockerTaskRuntimeManager(image=IMAGE, workspace_root=WORKSPACE_ROOT)
    return _manager


def _require_suly(authorization: str | None) -> None:
    if not SULY_TOKEN or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(503, "provisioner_auth_not_configured")
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


@app.on_event("startup")
def startup() -> None:
    if not SULY_TOKEN:
        raise RuntimeError("SULY_PROVISIONER_TOKEN is required")
    if not PUBLIC_GATEWAY_ORIGIN.startswith("https://"):
        raise RuntimeError("RUNTIME_GATEWAY_ORIGIN must be HTTPS")
    _db().close()


@app.post("/v1/runtimes", status_code=201)
def create_runtime(body: CreateRuntime, authorization: str | None = Header(default=None)):
    _require_suly(authorization)
    task_id, run_id = _identity(body.task_id), _identity(body.engine_run_id)
    if body.engine_id != "opencode":
        raise HTTPException(422, "engine_not_allowed")
    try:
        result = _manager().create(
            task_id=task_id, engine_run_id=run_id, engine_id=body.engine_id,
            files=[item.model_dump(exclude_none=True) for item in body.files],
        )
    except (ValueError, RuntimeErrorSafe) as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        with _db() as db:
            db.execute(
                "INSERT INTO runtimes (runtime_id,task_id,engine_run_id,engine_id,container_id,host_port,token_hash,expires_at,created_at,baseline_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (result["runtime_id"], task_id, run_id, body.engine_id,
                 result["container_id"], result["host_port"],
                 hashlib.sha256(result["access_token"].encode()).hexdigest(),
                 result["expires_at"], time.time(),
                 json.dumps({item.path: item.sha256 or hashlib.sha256(item.content.encode()).hexdigest() for item in body.files}, separators=(",", ":"))),
            )
    except Exception:
        _manager().destroy(runtime_id=result["runtime_id"], task_id=task_id, engine_run_id=run_id)
        raise HTTPException(503, "runtime_registration_failed")
    return {
        "runtime_id": result["runtime_id"], "task_id": task_id,
        "engine_run_id": run_id, "engine_id": body.engine_id,
        "base_url": f"{PUBLIC_GATEWAY_ORIGIN.rstrip('/')}/v1/runtime-gateway/{result['runtime_id']}",
        "access_token": result["access_token"], "expires_at": result["expires_at"],
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
        released = _manager().destroy(runtime_id=runtime_id, task_id=task_id, engine_run_id=run_id)
    except (ValueError, RuntimeErrorSafe) as exc:
        raise HTTPException(409, "runtime_release_rejected") from exc
    if released:
        with _db() as db:
            db.execute("DELETE FROM runtimes WHERE runtime_id=?", (runtime_id,))
    return {"released": released}


@app.api_route("/v1/runtime-gateway/{runtime_id}/{path:path}", methods=["GET", "POST"])
async def runtime_gateway(runtime_id: str, path: str, request: Request, authorization: str | None = Header(default=None)):
    row = _runtime(runtime_id, authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
    if request.method == "POST" and path == "execute":
        try:
            payload = ExecuteRequest.model_validate(await request.json())
        except Exception as exc:
            raise HTTPException(422, "invalid_execution_request") from exc
        return await execute(runtime_id, payload, authorization)
    route = "/" + path
    method = request.method
    if (method, route) not in _ALLOWED_PROXY:
        raise HTTPException(404, "route_not_allowed")
    body = await request.body()
    if len(body) > 65536:
        raise HTTPException(413, "request_too_large")
    headers = {"Accept": request.headers.get("accept", "application/json")}
    if body:
        headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{row['host_port']}",
            auth=("suly", _runtime_token_from_request(authorization)),
            timeout=httpx.Timeout(60, connect=3, read=55),
            follow_redirects=False, trust_env=False,
        ) as client:
            async with client.stream(method, route, content=body, headers=headers) as upstream:
                if 300 <= upstream.status_code < 400:
                    raise HTTPException(502, "upstream_redirect_rejected")
                chunks, total = [], 0
                async for chunk in upstream.aiter_bytes():
                    total += len(chunk)
                    if total > 2 * 1024 * 1024:
                        raise HTTPException(502, "upstream_response_too_large")
                    chunks.append(chunk)
                content = b"".join(chunks)
                safe_headers = {}
                for key in ("content-type", "cache-control"):
                    if key in upstream.headers:
                        safe_headers[key] = upstream.headers[key]
                return Response(content, status_code=upstream.status_code, headers=safe_headers)
    except httpx.HTTPError as exc:
        raise HTTPException(502, "runtime_unreachable") from exc


def _runtime_token_from_request(value: str | None) -> str:
    return value[7:] if value and value.startswith("Bearer ") else ""


@app.post("/v1/runtime-gateway/{runtime_id}/execute")
async def execute(runtime_id: str, body: ExecuteRequest, authorization: str | None = Header(default=None)):
    row = _runtime(runtime_id, _runtime_token_from_request(authorization))
    base = f"http://127.0.0.1:{row['host_port']}"
    auth = ("suly", _runtime_token_from_request(authorization))
    try:
        async with httpx.AsyncClient(base_url=base, auth=auth, timeout=httpx.Timeout(900, connect=5), trust_env=False) as client:
            session_id = body.session_id
            if session_id is None:
                created = await client.post("/api/session", json={
                    "title": body.title,
                    "permissions": [{"action": "*", "resource": "*", "effect": "ask"}],
                })
                created.raise_for_status()
                payload = created.json()
                session_id = payload.get("data", {}).get("id")
                if not isinstance(session_id, str) or not re.fullmatch(r"ses[A-Za-z0-9_-]{1,128}", session_id):
                    raise HTTPException(502, "invalid_session_response")
            if not re.fullmatch(r"ses[A-Za-z0-9_-]{1,128}", session_id):
                raise HTTPException(422, "invalid_session_id")
            result = await client.post(f"/api/session/{session_id}/prompt", json={"text": body.prompt})
            result.raise_for_status()
            return {"runtime_id": runtime_id, "session_id": session_id, "result": result.json()}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, "opencode_execution_failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "opencode_runtime_unreachable") from exc


@app.get("/v1/runtimes/{runtime_id}/results")
def runtime_results(runtime_id: str, authorization: str | None = Header(default=None)):
    row = _runtime(runtime_id, _runtime_token_from_request(authorization))
    try:
        container = _manager().client.containers.get(row["container_id"])
        stream, _stat = container.get_archive("/workspace")
        archive = BytesIO(b"".join(stream))
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
                "deleted_paths": deleted, "total_bytes": total, "files": files, "changed_files": changed}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "runtime_results_unavailable") from exc


@app.post("/internal/cleanup")
def cleanup(authorization: str | None = Header(default=None)):
    _require_suly(authorization)
    removed = _manager().cleanup_expired()
    with _db() as db:
        db.execute("DELETE FROM runtimes WHERE expires_at<=?", (time.time(),))
    return {"removed": removed}
