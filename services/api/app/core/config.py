from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SULY API"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"

    # Supabase client credentials. Secret keys are server-only.
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_secret_key: SecretStr | None = None

    # Exact, email-verified account allowed to manage the central AI provider.
    suly_owner_email: str | None = None

    # Server-side AI gateway: OpenAI-compatible providers or self-hosted Ollama. Disabled by default.
    ai_provider: str = "disabled"
    ai_base_url: str | None = None
    ai_api_key: SecretStr | None = None
    ai_model: str | None = None
    ai_timeout_seconds: float = Field(default=45.0, ge=5.0, le=180.0)
    ai_max_output_tokens: int = Field(default=1200, ge=64, le=8192)

    # Hermes Agent sidecar bridge is opt-in and disabled until its sandbox/tool policy is verified.
    hermes_agent_enabled: bool = False
    # Operator attestation only; this does not create isolation. Keep false until a per-task runtime manager exists.
    hermes_agent_isolation_confirmed: bool = False
    hermes_agent_base_url: str | None = None
    hermes_agent_api_key: SecretStr | None = None
    hermes_agent_model: str = "hermes-agent"
    hermes_agent_timeout_seconds: float = Field(default=90.0, ge=5.0, le=300.0)
    hermes_agent_max_output_chars: int = Field(default=12000, ge=256, le=50000)

    # SULY-owned explicit memory; keep disabled until its migration is applied.
    agent_memory_enabled: bool = False

    # Read-only credits API stays disabled until the ledger migration is reviewed/applied.
    engine_credits_enabled: bool = False

    # OpenCode must remain explicitly disabled; provisioner credentials alone cannot activate it.
    opencode_enabled: bool = False
    # Isolated runtime provider configuration. These values do not activate it unless opencode_enabled is true.
    runtime_provisioner_url: str | None = None
    runtime_provisioner_token: SecretStr | None = None
    runtime_provisioner_allowed_origins: list[str] = Field(default_factory=list)
    runtime_provisioner_timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)

    # In-process per-user API rate limits (requests per minute); 0 disables a limit.
    # Best-effort per API process; the ingress must still enforce global caps.
    rate_limit_chat_respond_per_minute: int = Field(default=10, ge=0, le=1000)
    rate_limit_chat_conversations_per_minute: int = Field(default=10, ge=0, le=1000)
    rate_limit_chat_messages_per_minute: int = Field(default=30, ge=0, le=1000)
    rate_limit_owner_ai_provider_per_minute: int = Field(default=5, ge=0, le=1000)

    # Worker runtime is opt-in; never starts merely because the API boots.
    worker_enabled: bool = False
    worker_lease_seconds: int = Field(default=90, ge=15, le=900)
    worker_poll_interval_seconds: float = Field(default=2.0, ge=0.1, le=60.0)

    # External engine stop reconciliation is opt-in until its migration is applied and runtime isolation is verified.
    engine_reconciler_enabled: bool = False
    engine_reconciler_interval_seconds: int = Field(default=30, ge=10, le=600)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
