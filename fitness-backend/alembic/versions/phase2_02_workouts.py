"""Create workouts, exercise_sets, derived_metrics.

Revision ID: phase2_02_workouts
Revises: phase2_01_users
Create Date: 2026-05-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "phase2_02_workouts"
down_revision: str | Sequence[str] | None = "phase2_01_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workouts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("workout_type", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_index("idx_workouts_user_id", "workouts", ["user_id"])
    op.create_index("idx_workouts_date", "workouts", ["date"])
    op.create_index("idx_workouts_client_id", "workouts", ["client_id"])

    op.create_table(
        "exercise_sets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_name", sa.String(), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column(
            "weight_unit",
            sa.String(),
            server_default=sa.text("'lbs'"),
            nullable=False,
        ),
        sa.Column("rpe", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workout_id"], ["workouts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_exercise_sets_workout_id", "exercise_sets", ["workout_id"])

    op.create_table(
        "derived_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_volume", sa.Float(), nullable=True),
        sa.Column("total_sets", sa.Integer(), nullable=True),
        sa.Column("total_reps", sa.Integer(), nullable=True),
        sa.Column("avg_rpe", sa.Float(), nullable=True),
        sa.Column("exercise_count", sa.Integer(), nullable=True),
        sa.Column("muscle_groups", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workout_id"], ["workouts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workout_id"),
    )


def downgrade() -> None:
    op.drop_table("derived_metrics")
    op.drop_table("exercise_sets")
    op.drop_index("idx_workouts_client_id", table_name="workouts")
    op.drop_index("idx_workouts_date", table_name="workouts")
    op.drop_index("idx_workouts_user_id", table_name="workouts")
    op.drop_table("workouts")
