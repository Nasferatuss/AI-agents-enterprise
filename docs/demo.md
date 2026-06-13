# 5-minute demo walkthrough

A guided tour of the Enterprise AI Agent Workbench MVP. Goal: understand the
whole platform — service-oriented core + 4 MVP modules — in 5–7 minutes.

## 0. Start (≈1 min)

```bash
make up            # postgres + qdrant + redis + api (Docker)   — OR —
make api           # just the gateway on :8000 (no Docker)
make seed          # populate the observability console with sample runs
make ui            # demo console on http://localhost:3000
```

> Without API keys / a local model the LLM-driven calls return a clear 503
> ("no provider succeeded"); the read-only views (schema, traces, search) work
> regardless. To make the agents answer for real, follow `docs/setup.md`
> (Ollama on the GPU box or any provider key in `.env`).

Open **http://localhost:3000** — three module cards:

## 1. Text-to-SQL BI Agent — `/text2sql` (≈2 min)

The clearest enterprise use case: a business question becomes SQL, runs against a
sandbox retail DB, and comes back with an explanation.

- Click an example chip, e.g. *"Top 3 customers by revenue from completed orders"*.
- Watch the **answer**, then each **generated SQL** + result table, then the
  **reasoning trace** (which model, latency, cost, tool calls).
- **The security story:** every query passes the read-only guards (ADR-004) —
  single SELECT, table allowlist, forced LIMIT, read-only connection. Ask
  something destructive ("delete all customers") and the guard rejects it; the
  agent recovers. See the adversarial suite in
  `apps/text2sql/tests/test_sql_injection.py`.

## 2. Workflow Orchestrator — `/workflows` (≈2 min)

Predictable, auditable workflows with a human-in-the-loop gate (ADR-007).

- Run the **access_request** workflow (resource + requester pre-filled).
- It validates, runs an LLM **risk assessment**, then **pauses** at the approval
  gate — *nothing is granted yet*.
- Read the risk assessment, then **Approve** or **Reject**. Approve runs the
  gated step; reject ends the run. Either way the decision lands in the **audit
  log** (who, when, why).

## 3. Observability Console — `/observability` (≈1 min)

Every agent, workflow, and eval run is traced (ADR-006).

- **Dashboard:** total runs, success rate, p95 latency, total cost.
- **Failure taxonomy:** non-successful runs grouped by kind/status.
- Click any row for the **full trace** — the step-by-step payload of that run.
- Go back to `/text2sql` or `/workflows`, run something, refresh here — the new
  trace appears.

## What this demonstrates

Not "the model answered" but the full engineering loop around the LLM:
**context → tools → reasoning → action → eval → trace → governance → demo.**
A model router (local-first, cost-aware), a RAG core with its own eval lab, a
guarded SQL agent, a predictable orchestrator with approval gates, and an
observability layer that captures all of it — on one service-oriented core.

See `wiki/00_index.md` for the architecture map and the decisions (ADRs) behind
each choice.
