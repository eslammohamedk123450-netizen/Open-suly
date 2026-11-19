from supabase import Client, create_client

from app.core.config import get_settings


def get_supabase_client(access_token: str | None = None) -> Client | None:
    """Create a request-scoped client using the project's publishable key.

    Pass the verified user's access token for RLS-scoped database requests.
    Never cache this client globally: doing so could leak one request's
    Authorization context into another user's request.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_publishable_key:
        return None

    client = create_client(
        settings.supabase_url,
        settings.supabase_publishable_key.get_secret_value(),
    )
    if access_token:
        client.postgrest.auth(access_token)
    return client


def get_supabase_admin_client() -> Client | None:
    """Create a server-only client for trusted writes that bypass user RLS.

    The secret key must be configured only in the API runtime environment.
    It must never be returned to or embedded in the Expo client.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_secret_key:
        return None
    return create_client(
        settings.supabase_url,
        settings.supabase_secret_key.get_secret_value(),
    )
