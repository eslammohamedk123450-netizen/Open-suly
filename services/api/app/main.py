from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.routers.agents import router as agents_router
from app.routers.chat import router as chat_router
from app.routers.projects import router as projects_router
from app.routers.project_files import router as project_files_router
from app.routers.tasks import router as tasks_router
from app.routers.tool_approvals import router as tool_approvals_router
from app.routers.opencode_sessions import router as opencode_sessions_router
from app.routers.opencode_tasks import router as opencode_tasks_router
from app.services.runtime_broker_contract import TaskScopedRuntimeBroker
from app.services.runtime_provisioner_http import HTTPSRuntimeLeaseProvider

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="SULY platform API",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

app.include_router(agents_router)
app.include_router(chat_router)
app.include_router(tasks_router)
app.include_router(projects_router)
app.include_router(project_files_router)
app.include_router(tool_approvals_router)
app.include_router(opencode_sessions_router)
app.include_router(opencode_tasks_router)

@app.on_event("startup")
def configure_opencode_runtime() -> None:
    """Enable the isolated runtime broker only with a complete explicit configuration."""
    current = get_settings()
    configured = (
        current.runtime_provisioner_url,
        current.runtime_provisioner_token,
        current.runtime_provisioner_allowed_origins,
    )
    app.state.runtime_broker = None
    app.state.runtime_provider = None
    if not any(configured):
        return
    if not all(configured):
        raise RuntimeError("OpenCode runtime provider configuration is incomplete")
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
