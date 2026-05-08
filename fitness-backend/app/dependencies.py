"""FastAPI dependency injection wiring (routers register dependencies in later phases)."""

from app.core.database import get_db_session

__all__ = ["get_db_session"]
