"""Remove legacy local memory tables now that Mem0 is the fixed backend."""
from __future__ import annotations

from alembic import op

revision = "004_remove_local_memory_tables"
down_revision = "003_terminal_event_cancelled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS team_memory")
    op.execute("DROP TABLE IF EXISTS user_memory")


def downgrade() -> None:
    # Deliberately no recreation: Mem0 is the architecture's source of truth.
    pass
