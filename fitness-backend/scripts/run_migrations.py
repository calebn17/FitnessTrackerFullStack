"""Apply Alembic migrations to head (wrapper for CI/scripts)."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
