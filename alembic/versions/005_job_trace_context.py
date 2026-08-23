"""Persist W3C trace context across the PostgreSQL worker queue.

Revision ID: 005_job_trace_context
Revises: 004_remove_local_memory_tables
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "005_job_trace_context"
down_revision = "004_remove_local_memory_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "trace_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "trace_context")
