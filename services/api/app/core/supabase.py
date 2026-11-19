from supabase import Client, create_client

from app.core.config import get_settings


def get_supabase_client(access_token: str | None = None) -> Client | None:
    """Create a request-scoped client using the project's publishable key.

    Pass the verified user's Supabase access token for RLS-scoped database
    requests. Never cache this client globally: doing so could leak one
    request's Authorization context into another user's request.

    This client deliberately does not use a secret/service-role key.
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
