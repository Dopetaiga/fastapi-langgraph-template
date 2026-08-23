"""Align approval status storage with the ORM enum.

Revision ID: 002_approval_status_enum
"""
from __future__ import annotations

from alembic import op

revision = "002_approval_status_enum"
down_revision = "001_add_phase5_8_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE approval_status AS ENUM "
        "('pending', 'approved', 'rejected', 'expired')"
    )
    op.alter_column("approvals", "status", server_default=None)
    op.execute(
        "ALTER TABLE approvals ALTER COLUMN status TYPE approval_status "
        "USING status::text::approval_status"
    )
    op.alter_column("approvals", "status", server_default="pending")


def downgrade() -> None:
    op.alter_column("approvals", "status", server_default=None)
    op.execute(
        "ALTER TABLE approvals ALTER COLUMN status TYPE varchar "
        "USING status::text"
    )
    op.alter_column("approvals", "status", server_default="pending")
    op.execute("DROP TYPE approval_status")
