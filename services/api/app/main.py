from fastapi import Depends, FastAPI

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.routers.chat import router as chat_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="SULY platform API",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

app.include_router(chat_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness endpoint; does not expose credentials or claim DB readiness."""
    return {
        "status": "ok",
        "service": "suly-api",
        "version": app.version,
    }


@app.get("/v1/auth/me", tags=["auth"])
def auth_me(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, str | None]:
    """Return the identity validated by Supabase Auth; never expose user metadata."""
    return {"id": user.id, "email": user.email}
