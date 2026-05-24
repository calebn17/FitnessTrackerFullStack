"""Application settings loaded from environment variables."""

from functools import lru_cache

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
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    # Database (used in later phases)
    database_url: str = "postgresql+asyncpg://fitness:fitness@localhost:5433/fitness"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 1800

    # Redis (used in later phases)
    redis_url: str = "redis://localhost:6379/0"

    # Supabase auth (Phase 3 JWT validation)
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    # Phase 8 — CORS (comma-separated origins; empty uses dev/test defaults below)
    cors_allowed_origins: str = ""
    cors_allow_credentials: bool = True

    # Phase 8 — rate limits (SlowAPI strings; mirror router decorators)
    rate_limit_read: str = "100/minute"
    rate_limit_write: str = "20/minute"

    # Strava OAuth (LifeDashboard integrations)
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/api/v1/auth/strava/callback"

    # Whoop OAuth
    whoop_client_id: str = ""
    whoop_client_secret: str = ""
    whoop_redirect_uri: str = "http://localhost:8000/api/v1/auth/whoop/callback"

    # On-demand provider sync staleness threshold
    sync_staleness_minutes: int = 15

    def strava_configured(self) -> bool:
        return bool(self.strava_client_id.strip() and self.strava_client_secret.strip())

    def whoop_configured(self) -> bool:
        return bool(self.whoop_client_id.strip() and self.whoop_client_secret.strip())

    def cors_origin_list(self) -> list[str]:
        """Parse ``cors_allowed_origins`` as comma-separated URLs."""
        return [p.strip() for p in self.cors_allowed_origins.split(",") if p.strip()]

    def resolved_cors_origins(self) -> list[str]:
        """Origins allowed by CORS middleware (explicit list wins)."""
        explicit = self.cors_origin_list()
        if explicit:
            return explicit
        if self.environment in ("development", "test"):
            return [
                "http://localhost:3000",
                "http://localhost:8080",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8080",
            ]
        return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return settings instance (suitable for FastAPI Depends caching)."""
    return Settings()
