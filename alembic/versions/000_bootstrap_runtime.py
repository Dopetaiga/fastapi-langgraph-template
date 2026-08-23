"""Bootstrap application runtime tables.

Revision ID: 000_bootstrap_runtime
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "000_bootstrap_runtime"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_status = sa.Enum(
        "queued", "running", "paused", "completed", "failed", "cancelled",
        name="run_status",
    )
    job_status = sa.Enum(
        "queued", "running", "retry_wait", "completed", "failed",
        name="job_status",
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("team_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_sessions_team_id", "sessions", ["team_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("graph_name", sa.String(), nullable=False),
        sa.Column("graph_version", sa.String(), nullable=False, server_default="1"),
        sa.Column("graph_definition_hash", sa.String(), nullable=True),
        sa.Column("graph_snapshot", JSONB, nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("step_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("termination_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_runs_session_id", "runs", ["session_id"])
    op.create_index("ix_runs_status", "runs", ["status"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("lease_owner", sa.String(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for name, columns in (
        ("ix_jobs_run_id", ["run_id"]),
        ("ix_jobs_status", ["status"]),
        ("ix_jobs_lease_owner", ["lease_owner"]),
        ("ix_jobs_lease_expires_at", ["lease_expires_at"]),
        ("ix_jobs_next_attempt_at", ["next_attempt_at"]),
    ):
        op.create_index(name, "jobs", columns)

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("node", sa.String(), nullable=True),
        sa.Column("payload", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "seq", name="uq_run_event_seq"),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_index("ix_run_events_type", "run_events", ["type"])
    op.create_index(
        "uq_run_terminal_event",
        "run_events",
        ["run_id"],
        unique=True,
        postgresql_where=sa.text("type IN ('run.completed', 'run.failed')"),
    )


def downgrade() -> None:
    op.drop_table("run_events")
    op.drop_table("jobs")
    op.drop_table("runs")
    op.drop_table("sessions")
    sa.Enum(name="job_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="run_status").drop(op.get_bind(), checkfirst=True)
