from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="SULY platform API",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness endpoint; does not expose credentials or claim DB readiness."""
    return {
        "status": "ok",
        "service": "suly-api",
        "version": app.version,
    }
