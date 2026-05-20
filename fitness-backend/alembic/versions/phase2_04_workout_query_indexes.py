"""Add composite indexes for common workout list and sync queries.

Revision ID: phase2_04_workout_query_indexes
Revises: phase2_03_insights
Create Date: 2026-05-17

"""

from collections.abc import Sequence

from alembic import op

revision: str = "phase2_04_workout_query_indexes"
down_revision: str | Sequence[str] | None = "phase2_03_insights"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_workouts_user_deleted_date",
        "workouts",
        ["user_id", "deleted_at", "date"],
        unique=False,
    )
    op.create_index(
        "idx_workouts_user_client",
        "workouts",
        ["user_id", "client_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_workouts_user_client", table_name="workouts")
    op.drop_index("idx_workouts_user_deleted_date", table_name="workouts")
