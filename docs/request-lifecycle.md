# A request, end to end — one worked example

A concrete trace of a single request through every layer, with the real fields the
platform records. Pairs with [`ARCHITECTURE.md`](ARCHITECTURE.md) (the map); this is
one trip through it. The example is a Text-to-SQL question, because it exercises the
most layers: gateway → router tier decision → tool gateway allowlist → SQL guard →
trace write.

> **Request:** `POST /v1/apps/text2sql/ask` `{"question": "What were total sales by
> region last quarter?"}`

## The path

```
①  POST /v1/apps/text2sql/ask
        │
②  Gateway middleware  (platform/gateway/security.py)
        │   SecurityHeaders (always) → RateLimit (if WB_RATE_LIMIT_PER_MIN) →
        │   ApiKey (if WB_API_KEY, hmac.compare_digest) → CORS
        ▼
③  ask()  (apps/text2sql/api.py)
        │   build_agent(engine): run_sql tool + the reflected schema in instructions
        ▼
④  run_agent()  (platform/runtime/agent.py) — the agentic loop, up to max_steps=6
        │   step 1: router.step(complexity="standard") → model emits a run_sql tool call
        ▼
⑤  ModelRouter.step()  (platform/runtime/router.py)
        │   chain("standard") = deepseek → kimi → anthropic → openai  (local off w/o pull)
        │   first healthy candidate serves; on ProviderCallError → cooldown + next
        │   → deepseek-chat answers     [cost $0.000436 · 4211 ms · 1 fallback=no]
        ▼
⑥  run_sql tool  (platform/capabilities/sql_guard.py)
        │   validate_sql(): sqlglot AST (SELECT-only) · function denylist · table
        │   allowlist · forced LIMIT 200 → executed on a READ-ONLY connection
        │   → rows returned to the model as a tool result
        ▼
④' step 2: router.step() with the tool result → model writes the final answer (no tool call) → loop ends
        ▼
⑦  record_agent_run()  (platform/runtime/tracing.py)
        │   _scrub_payload(): raw SQL rows → "[redacted: N rows]"
        │   safe_record(): best-effort — a trace-store outage logs a warning, never 500s
        ▼
⑧  200 OK  { answer, sql_calls, run }     +  one row in the `traces` table
```

## The trace it writes

One row in the `traces` table (`platform/observability/models.py`). Numbers below are
from the live routing benchmark's `sql-1` case (standard tier → DeepSeek; see
[`benchmarks.md`](benchmarks.md)):

```json
{
  "id": "9f2a1c7b04e5d318",
  "kind": "agent",
  "name": "text2sql",
  "status": "completed",
  "created_at": "2026-06-20T18:22:41.704812Z",
  "latency_ms": 4211,
  "cost_usd": 0.000436,
  "input_tokens": 512,
  "output_tokens": 96,
  "num_steps": 2,
  "error": null,
  "payload": {
    "final_text": "Total sales by region last quarter: West $1.24M, East $0.98M, …",
    "steps": [
      {
        "tool_executions": [
          {
            "name": "run_sql",
            "result": {
              "sql": "SELECT region, SUM(amount) AS total FROM sales WHERE … GROUP BY region LIMIT 200",
              "columns": ["region", "total"],
              "rows": "[redacted: 4 rows]",
              "row_count": 4
            }
          }
        ]
      }
    ]
  }
}
```

## What each field proves

| Field | Where it comes from | Why it matters |
|---|---|---|
| `cost_usd` `0.000436` | router summed per-call cost (`pricing.py`) | the standard-tier query went to the **cheap** provider, not frontier — ~60× cheaper than `claude-opus-4-8` would have been on the same tokens |
| `latency_ms` `4211` | router per-call `time.monotonic()` | cheap tier also served it in ~4 s vs frontier's 11–16 s |
| `num_steps` `2` | the agent loop | one tool-call turn + one final-answer turn; the loop is capped at `max_steps=6` |
| `rows` `"[redacted: 4 rows]"` | `_scrub_payload` | the trace is useful (SQL, columns, count) but never stores raw customer data |
| `status` `completed` | terminal state | only terminal runs are written to `traces`; in-flight state lives in `agent_runs` |
| trace exists at all | `safe_record` best-effort | if the trace DB had been down, the user would still have gotten their answer — telemetry is never on the critical path |

## The same request, three ways it could have gone differently

- **Provider down.** If DeepSeek had 500'd, the router would mark it unhealthy (30 s
  cooldown) and fall through to the next candidate; the trace would show `num_steps`
  unchanged but the winning `provider` would be `anthropic`, and the cost/latency
  would jump accordingly. (Cost benchmark `classify-1` captured exactly this fallback.)
- **Malicious SQL.** Had the model emitted `DELETE FROM sales` (prompt injection), the
  SQL guard rejects it at the AST stage; the agent sees a normal tool error and
  recovers — no write reaches the read-only connection.
- **Async flagship instead.** The autonomous agent runs this same shape but via
  `POST /runs → 202` + a background job + poll, with the live state in `agent_runs`
  (heartbeated) rather than inline — see [`distributed.md`](distributed.md).
