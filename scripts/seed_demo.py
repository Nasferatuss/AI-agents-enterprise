"""Seed the trace store with sample runs so the Observability Console has content
to show in a demo (UX QA, Phase 4).

Usage:
    uv run python scripts/seed_demo.py

Writes to WB_TRACE_DB_URL (default: local sqlite data/traces.db; Postgres under
`make up`). Idempotent enough for demos — re-running just appends more samples.
"""

import asyncio

from workbench_observability import init_db, record_trace

_SAMPLES = [
    dict(
        kind="agent",
        name="text2sql",
        status="completed",
        latency_ms=1840,
        cost_usd=0.0021,
        input_tokens=920,
        output_tokens=140,
        num_steps=2,
        payload={"final_text": "There are 10 customers.", "note": "seeded sample"},
    ),
    dict(
        kind="agent",
        name="demo",
        status="completed",
        latency_ms=2210,
        cost_usd=0.0009,
        input_tokens=410,
        output_tokens=88,
        num_steps=2,
        payload={"final_text": "23.5 * 17 - 4 = 395.5", "note": "seeded sample"},
    ),
    dict(
        kind="workflow",
        name="content_brief",
        status="completed",
        latency_ms=5300,
        num_steps=4,
        payload={"note": "draft → judge review → finalize"},
    ),
    dict(
        kind="workflow",
        name="access_request",
        status="rejected",
        latency_ms=1200,
        num_steps=2,
        error="step 'grant' rejected by security-officer",
        payload={"note": "human rejected the access grant at the approval gate"},
    ),
    dict(
        kind="eval",
        name="synthetic-kb",
        status="completed",
        cost_usd=0.034,
        num_steps=6,
        payload={"aggregates": {"hit_rate": 0.83, "faithfulness": 0.79}},
    ),
    dict(
        kind="agent",
        name="text2sql",
        status="max_steps_reached",
        latency_ms=9100,
        cost_usd=0.0044,
        input_tokens=2100,
        output_tokens=300,
        num_steps=6,
        error="max_steps_reached",
        payload={"note": "agent looped on an ambiguous question"},
    ),
    # synthetic failed traces for the Incident Response demo (one per failure mode)
    dict(
        kind="agent",
        name="text2sql",
        status="failed",
        latency_ms=600,
        num_steps=1,
        error="execution failed: no such column: revnue",
        payload={"note": "model referenced a misspelled column"},
    ),
    dict(
        kind="agent",
        name="deep_research",
        status="failed",
        latency_ms=200,
        error="no provider succeeded for complexity=complex; tried: none",
        payload={"note": "no model provider available"},
    ),
    dict(
        kind="eval",
        name="synthetic-stale",
        status="failed",
        cost_usd=0.01,
        num_steps=6,
        error="low retrieval quality",
        payload={"aggregates": {"hit_rate": 0.33, "faithfulness": 0.4}},
    ),
]


async def main() -> None:
    await init_db()
    for sample in _SAMPLES:
        await record_trace(**sample)
    print(f"seeded {len(_SAMPLES)} sample traces — open /observability to view")


if __name__ == "__main__":
    asyncio.run(main())
