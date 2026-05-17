"""FastAPI dependency injection wiring (routers register dependencies in later phases)."""

from app.config import get_settings
from app.core.database import get_db_session
from app.core.security import get_supabase_jwt_claims

__all__ = [
    "get_db_session",
    "get_settings",
    "get_supabase_jwt_claims",
]
