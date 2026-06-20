"""unique (kind, idempotency_key) on agent_runs — race-safe idempotency

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The plain index is now redundant with the unique constraint (which has its
    # own backing index); replace it with the constraint so a concurrent duplicate
    # submit fails at the DB instead of racing through the application-level check.
    op.drop_index("ix_agent_runs_idempotency_key", table_name="agent_runs")
    op.create_unique_constraint(
        "uq_agent_runs_kind_idempotency", "agent_runs", ["kind", "idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_agent_runs_kind_idempotency", "agent_runs", type_="unique")
    op.create_index("ix_agent_runs_idempotency_key", "agent_runs", ["idempotency_key"])
