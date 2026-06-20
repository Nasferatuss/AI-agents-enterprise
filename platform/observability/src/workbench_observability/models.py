"""Trace ORM model — the minimal custom trace schema (ADR-006).

One row per run (agent / workflow / eval). Queryable aggregate columns drive the
list and dashboard views; the full serialized run lives in `payload` for the
step-by-step detail view. This is deliberately not a normalized
run→step→toolcall→modelcall set of tables — "custom schema, not a LangSmith clone".
"""

from sqlalchemy import JSON, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from workbench_observability.db import Base


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # agent | workflow | eval
    name: Mapped[str] = mapped_column(String(128))  # agent/workflow/dataset name
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)  # ISO, microsecond
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    num_steps: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # full serialized run


class AgentRun(Base):
    """Durable run state for long-lived runs (durability hardening).

    Unlike `Trace` (a terminal, read-only record of a finished run), this is the
    *live* state of a run that must survive a restart: a workflow paused at a
    human-in-the-loop gate (`awaiting_approval` for hours), or an async flagship
    run being polled (`pending` → `running` → terminal). The serialized domain
    object lives in `payload`; `idempotency_key` dedupes expensive submissions.
    """

    __tablename__ = "agent_runs"
    # Enforce idempotency at the schema level: a (kind, idempotency_key) pair is
    # unique, so two concurrent submits with the same key can't both create a run
    # (the loser hits IntegrityError → caller returns the winner). NULL keys are
    # distinct in SQL, so un-keyed runs are unaffected.
    __table_args__ = (
        UniqueConstraint("kind", "idempotency_key", name="uq_agent_runs_kind_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # workflow | autonomous | …
    status: Mapped[str] = mapped_column(String(32), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # serialized domain object
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)  # ISO, microsecond
    updated_at: Mapped[str] = mapped_column(String(40))
