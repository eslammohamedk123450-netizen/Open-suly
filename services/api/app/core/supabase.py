from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


@lru_cache
def get_supabase_client() -> Client | None:
    """Create an anon-key client; user data access must still be scoped by RLS.

    Never replace the anon key with a service-role key in this application
    configuration. User-scoped authorization is added with the auth layer.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        return None

    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key.get_secret_value(),
    )
