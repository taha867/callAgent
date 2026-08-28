import re

from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROLE_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class Config(BaseSettings):
    """Global, cross-domain settings. A domain that genuinely needs its own settings
    (voice/config.py, added in Phase 2) gets its own small BaseSettings subclass instead
    of bloating this one."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: PostgresDsn
    MIGRATION_DATABASE_URL: PostgresDsn | None = None
    APP_DB_ROLE: str = "callagent_app"
    REDIS_URL: RedisDsn

    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = []

    TEMPORAL_HOST: str = "localhost:7233"
    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "callagent-main"

    # spec §2.2.1's recommended configuration — calls/activities.py::with_runtime_recovery
    # uses this as the soft-wait threshold before treating a dependency call as unavailable.
    BACKEND_SOFT_WAIT_MS: int = 1500

    # Idempotency wrapper tuning — src/idempotency.py
    IDEMPOTENCY_POLL_ATTEMPTS: int = 15
    IDEMPOTENCY_POLL_INTERVAL_SECONDS: float = 0.2

    # Kill switch — spec §39
    GLOBAL_OUTBOUND_ENABLED: bool = True
    CAMPAIGN_ENABLED: bool = True
    CLI_ENABLED: bool = True
    AI_AUTOMATION_ENABLED: bool = True
    HUMAN_FALLBACK_AVAILABLE: bool = True

    @field_validator("APP_DB_ROLE")
    @classmethod
    def _validate_app_db_role(cls, value: str) -> str:
        # This value is interpolated into raw SQL by the audit-grants migration
        # (migrations/versions/*_audit_event_insert_only_grants.py). Validating it here,
        # at the single point every consumer reads it from, is the injection guard.
        if not _ROLE_NAME_PATTERN.fullmatch(value):
            raise ValueError(f"unsafe Postgres role name: {value!r}")
        return value

    @property
    def migration_url(self) -> str:
        return str(self.MIGRATION_DATABASE_URL or self.DATABASE_URL)


settings = Config()  # type: ignore[call-arg]
