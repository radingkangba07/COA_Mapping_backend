import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    """Pick the .env file based on APP_ENV (testing | staging | production).

    Falls back to `.env` for local development when APP_ENV is unset.
    """
    app_env = os.getenv("APP_ENV", "").lower()
    if app_env in ("testing", "staging", "production"):
        return f".env.{app_env}"
    return ".env"


class Settings(BaseSettings):
    # Environment
    app_env: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://coa_user:coa_pass@localhost:5432/coa_migration"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Auth (JWT)
    jwt_secret: str = "secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # NATS JetStream (empty = disabled, sync fallback)
    nats_url: str = ""
    nats_stream_name: str = "COA_JOBS"

    # S3-Compatible Storage (DigitalOcean Spaces in production, MinIO for local dev)
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "coa-storage"
    s3_region: str = "us-east-1"

    # Email (Resend) — empty api key = disabled, logs URL instead
    resend_api_key: str = ""
    from_email: str = ""
    app_url: str = ""

    # App
    app_name: str = "coa-migration"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
