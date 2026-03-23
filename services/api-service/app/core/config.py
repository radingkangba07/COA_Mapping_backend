"""Application configuration settings."""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "COA Migration API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://coa_user:coa_password@localhost:5432/coa_migration"
    )
    DATABASE_URL_SYNC: str = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://coa_user:coa_password@localhost:5432/coa_migration"
    )
    
    # RabbitMQ (for future ML service integration)
    RABBITMQ_URL: str = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    
    # Queue names
    QUEUE_MATCHING_JOBS: str = "coa.matching.jobs"
    QUEUE_MATCHING_RESULTS: str = "coa.matching.results"
    
    # CORS
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")
    
    # MongoDB (legacy - for migration period)
    MONGO_URL: str = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    DB_NAME: str = os.environ.get("DB_NAME", "test_database")
    
    # Object Storage
    STORAGE_PROVIDER: str = os.environ.get("STORAGE_PROVIDER", "emergent")
    STORAGE_APP_NAME: str = os.environ.get("STORAGE_APP_NAME", "coa-migration")
    EMERGENT_LLM_KEY: str = os.environ.get("EMERGENT_LLM_KEY", "")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Allow extra fields from .env


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
