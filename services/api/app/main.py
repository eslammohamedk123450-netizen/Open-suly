from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlsplit
from uuid import uuid4

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.ratelimit import RateLimitExceeded, apply_rate_limit
from app.routers.agents import router as agents_router
from app.routers.chat import router as chat_router
from app.routers.projects import router as projects_router
from app.routers.project_files import router as project_files_router
from app.routers.tasks import router as tasks_router
from app.routers.tool_approvals import router as tool_approvals_router
from app.routers.opencode_sessions import router as opencode_sessions_router
from app.routers.opencode_tasks import router as opencode_tasks_router
from app.routers.engine_collaboration import router as engine_collaboration_router
from app.routers.agent_memories import router as agent_memories_router
from app.services.runtime_broker_contract import TaskScopedRuntimeBroker
from app.services.runtime_provisioner_http import HTTPSRuntimeLeaseProvider

settings = get_settings()


def _validate_production_settings(current) -> None:
    """Fail closed before serving traffic when production secrets are incomplete."""
    if getattr(current, "app_env", "development") != "production":
        return
    required = {
        "SUPABASE_URL": current.supabase_url,
        "SUPABASE_PUBLISHABLE_KEY": current.supabase_publishable_key,
        "SUPABASE_SECRET_KEY": current.supabase_secret_key,
    }
    missing = []
    for name, value in required.items():
        if value is None or (hasattr(value, "get_secret_value") and not value.get_secret_value()):
            missing.append(name)
    if missing:
        raise RuntimeError("Missing required production settings: " + ", ".join(missing))
    parsed = urlsplit(current.supabase_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("Production SUPABASE_URL must be an HTTPS URL without embedded credentials")
    if parsed.query or parsed.fragment:
        raise RuntimeError("Production SUPABASE_URL must not contain a query or fragment")
    if getattr(current, "ai_provider", "disabled") not in {"disabled", "ollama", "openai-compatible"}:
        raise RuntimeError("AI_PROVIDER is not supported")

def _validated_cors_origins(origins: list[str], app_env: str) -> list[str]:
    """Accept only exact origins; wildcard and malformed origins fail closed."""
    if not isinstance(origins, list):
        raise RuntimeError("CORS_ALLOWED_ORIGINS must be a JSON array of exact origins")
    validated: list[str] = []
    for origin in origins:
        if not isinstance(origin, str) or not origin or origin == "*" or origin != origin.strip():
            raise RuntimeError("CORS_ALLOWED_ORIGINS contains an invalid origin")
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise RuntimeError("CORS_ALLOWED_ORIGINS must contain origin-only URLs")
        if app_env == "production" and parsed.scheme != "https":
            raise RuntimeError("Production CORS origins must use HTTPS")
        if origin.rstrip("/") in {item.rstrip("/") for item in validated}:
            raise RuntimeError("CORS_ALLOWED_ORIGINS contains a duplicate origin")
        validated.append(origin.rstrip("/"))
    return validated


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="SULY platform API",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
) 

cors_origins = _validated_cors_origins(settings.cors_allowed_origins, settings.app_env)
@app.middleware("http")
async def add_security_headers(request, call_next):
    """Apply conservative browser security headers without trusting client input."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers["X-Request-ID"] = str(uuid4())
    if settings.app_env == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response

if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Client-Info", "apikey"],
        max_age=600,
    )

app.include_router(agents_router)
app.include_router(chat_router)
app.include_router(tasks_router)
app.include_router(projects_router)
app.include_router(project_files_router)
app.include_router(tool_approvals_router)
app.include_router(opencode_sessions_router)
app.include_router(opencode_tasks_router)
app.include_router(engine_collaboration_router)
app.include_router(agent_memories_router)

@app.on_event("startup")
def configure_opencode_runtime() -> None:
    """Enable the isolated runtime broker only with a complete explicit configuration."""
    current = get_settings()
    _validate_production_settings(current)
    app.state.runtime_broker = None
    app.state.runtime_provider = None
    # Both engines use the same trusted provisioner contract, but receive
    # distinct engine IDs and fresh task-attempt runtimes.
    if not current.opencode_enabled and not current.hermes_agent_enabled:
        return
    configured = (
        current.runtime_provisioner_url,
        current.runtime_provisioner_token,
        current.runtime_provisioner_allowed_origins,
    )
    if not all(configured):
        raise RuntimeError("Isolated engine runtime provider configuration is incomplete")
    allowed = frozenset(current.runtime_provisioner_allowed_origins)
    provider = HTTPSRuntimeLeaseProvider(
        base_url=current.runtime_provisioner_url,
        bearer_token=current.runtime_provisioner_token.get_secret_value(),
        allowed_origins=allowed,
        timeout_seconds=current.runtime_provisioner_timeout_seconds,
    )
    app.state.runtime_provider = provider
    app.state.runtime_broker = TaskScopedRuntimeBroker(
        provider, allowed_origins=allowed
    )


@app.on_event("shutdown")
def close_opencode_runtime_provider() -> None:
    provider = getattr(app.state, "runtime_provider", None)
    if provider is not None:
        provider.close()



def rate_limit_dependency(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Apply the per-user API rate limit after authentication.

    Unauthenticated probes are not rate-limited here on purpose: they are
    already rejected with 401 by the authentication dependency, and
    anonymous floods must be handled at the reverse proxy layer.
    """
    apply_rate_limit(user.id)
    return user


# Scope a stricter limit to the AI gateway endpoints.
def ai_rate_limit_dependency(
    user: AuthenticatedUser = Depends(rate_limit_dependency),
) -> AuthenticatedUser:
    """Apply a stricter per-user limit on provider-backed endpoints.

    The AI gateway has a smaller budget because each accepted request can
    consume provider tokens and long-running worker capacity.
    """
    apply_rate_limit(f"ai:{user.id}", capacity=6, refill_seconds=10.0)
    return user


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(
    _request, exc: RateLimitExceeded
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again shortly."},
        headers={
            "Retry-After": str(max(1, int(exc.retry_after) + 1)),
            "X-RateLimit-Remaining": "0",
        },
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness endpoint; does not expose credentials or claim DB readiness."""
    return {
        "status": "ok",
        "service": "suly-api",
        "version": app.version,
    }


@app.get("/ready", tags=["health"])
async def readiness() -> JSONResponse:
    """Check required Supabase connection configuration, without probing live services.

    هذا فحص إعدادات فقط؛ لا يثبت إمكانية الوصول إلى الشبكة أو صحة قاعدة البيانات.
    """
    current = get_settings()
    # نتحقق من وجود الإعدادات الأساسية فقط، ولا نعرض قيم المفاتيح أو العناوين.
    missing = []
    if not current.supabase_url:
        missing.append("supabase_url")
    if not current.supabase_publishable_key:
        missing.append("supabase_publishable_key")
    # Auth validation uses the publishable key, while trusted conversation,
    # task, approval, and worker operations require the server-only secret.
    if not current.supabase_secret_key:
        missing.append("supabase_secret_key")

    configured = not missing
    return JSONResponse(
        status_code=200 if configured else 503,
        content={
            "status": "ready" if configured else "not_ready",
            "service": "suly-api",
            "check": "configuration_only",
            "supabase": "configured" if configured else "missing_required_configuration",
            "missing": missing,
        },
    )


@app.get("/v1/auth/me", tags=["auth"])
def auth_me(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, str | None]:
    """Return the identity validated by Supabase Auth; never expose user metadata."""
    return {"id": user.id, "email": user.email}
