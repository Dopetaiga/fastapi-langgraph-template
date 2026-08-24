"""Freeze the resolved model decision into each Run.

Revision ID: 006_run_model_decision
Revises: 005_job_trace_context
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "006_run_model_decision"
down_revision = "005_job_trace_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("model_decision", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "model_decision")
