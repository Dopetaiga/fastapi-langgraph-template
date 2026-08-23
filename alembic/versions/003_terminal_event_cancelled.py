"""Include cancellation in the one-terminal-event invariant."""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "003_terminal_event_cancelled"
down_revision = "002_approval_status_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_run_terminal_event", table_name="run_events")
    op.create_index(
        "uq_run_terminal_event",
        "run_events",
        ["run_id"],
        unique=True,
        postgresql_where=sa.text(
            "type IN ('run.completed', 'run.failed', 'run.cancelled')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_run_terminal_event", table_name="run_events")
    op.create_index(
        "uq_run_terminal_event",
        "run_events",
        ["run_id"],
        unique=True,
        postgresql_where=sa.text("type IN ('run.completed', 'run.failed')"),
    )
