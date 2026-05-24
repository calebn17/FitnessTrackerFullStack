"""Add oauth_tokens, strava_activities, and daily_health_records.

Revision ID: phase2_05_integrations
Revises: phase2_04_workout_query_indexes
Create Date: 2026-05-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "phase2_05_integrations"
down_revision: str | Sequence[str] | None = "phase2_04_workout_query_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("athlete_id", sa.String(), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_tokens_user_provider"),
    )

    op.create_table(
        "strava_activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strava_id", sa.BigInteger(), nullable=False),
        sa.Column("sport_type", sa.String(), nullable=False),
        sa.Column("start_date_local", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distance", sa.Float(), nullable=False),
        sa.Column("moving_time", sa.Integer(), nullable=False),
        sa.Column("elapsed_time", sa.Integer(), nullable=False),
        sa.Column("average_speed", sa.Float(), nullable=False),
        sa.Column("max_speed", sa.Float(), nullable=True),
        sa.Column("total_elevation_gain", sa.Float(), nullable=False),
        sa.Column("average_heartrate", sa.Float(), nullable=True),
        sa.Column("max_heartrate", sa.Float(), nullable=True),
        sa.Column("average_cadence", sa.Float(), nullable=True),
        sa.Column("calories", sa.Float(), nullable=True),
        sa.Column("pr_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strava_id"),
    )
    op.create_index(
        "idx_strava_activities_user_start",
        "strava_activities",
        ["user_id", "start_date_local"],
    )

    op.create_table(
        "daily_health_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("sleep_score", sa.Integer(), nullable=True),
        sa.Column("total_sleep_seconds", sa.Integer(), nullable=True),
        sa.Column("deep_sleep_seconds", sa.Integer(), nullable=True),
        sa.Column("rem_sleep_seconds", sa.Integer(), nullable=True),
        sa.Column("light_sleep_seconds", sa.Integer(), nullable=True),
        sa.Column("sleep_efficiency", sa.Float(), nullable=True),
        sa.Column("recovery_score", sa.Integer(), nullable=True),
        sa.Column("resting_heart_rate", sa.Float(), nullable=True),
        sa.Column("hrv", sa.Float(), nullable=True),
        sa.Column("spo2", sa.Float(), nullable=True),
        sa.Column("strain_score", sa.Float(), nullable=True),
        sa.Column("active_calories", sa.Integer(), nullable=True),
        sa.Column("total_calories", sa.Integer(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "date",
            "provider",
            name="uq_daily_health_user_date_provider",
        ),
    )
    op.create_index(
        "idx_daily_health_records_user_date",
        "daily_health_records",
        ["user_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("idx_daily_health_records_user_date", table_name="daily_health_records")
    op.drop_table("daily_health_records")
    op.drop_index("idx_strava_activities_user_start", table_name="strava_activities")
    op.drop_table("strava_activities")
    op.drop_table("oauth_tokens")
