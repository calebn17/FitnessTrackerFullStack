"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Fitness Platform API"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database (used in later phases)
    database_url: str = "postgresql+asyncpg://fitness:fitness@localhost:5432/fitness"

    # Redis (used in later phases)
    redis_url: str = "redis://localhost:6379/0"

    # Supabase auth (Phase 3 JWT validation)
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"


def get_settings() -> Settings:
    """Return settings instance (suitable for FastAPI Depends caching)."""
    return Settings()
