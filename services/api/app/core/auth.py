from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.supabase import get_supabase_client


_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None
    email_verified: bool = False


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    """Validate the bearer JWT with Supabase Auth; never trust decoded claims alone."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client = get_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured",
        )

    try:
        # get_user(jwt) asks Supabase Auth to validate the token against the
        # Auth service. The client is request-scoped and closed immediately.
        with client:
            response = client.auth.get_user(credentials.credentials)
            user = response.user
    except Exception as exc:
        # supabase-py delegates Auth errors to its GoTrue dependency and does
        # not expose a stable SupabaseAPIError symbol across releases.
        error_status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if error_status in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
        ) from exc

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        id=str(user.id),
        email=getattr(user, "email", None),
        email_verified=bool(getattr(user, "email_confirmed_at", None)),
    )
