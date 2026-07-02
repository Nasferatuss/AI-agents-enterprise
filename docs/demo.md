# 5-minute demo walkthrough

A guided tour of the Enterprise AI Agent Workbench. Goal: see the "wow" tier (the
externally-connected flagships) *and* the engineering rigor underneath — in 5–7
minutes. Lead with the flagships if you have a reviewer's attention for only two.

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
> (Ollama on the GPU box or any provider key in `.env`). The live web/browser
> flagships also need `WB_RESEARCH_LIVE_WEB=true` / a Chromium install.

Open **http://localhost:3000** — one card per module. Suggested path below.

## The flagships (the "wow" tier — lead here)

### 1. Autonomous Agent — `/autonomous` (≈2 min)

A real `plan → act (tools) → reflect → repeat` loop until the goal is met, over a
governed toolset (live web, read-only SQL, a sandboxed file workspace).

- Give it a goal, e.g. *"Research retrieval-augmented generation and write a short
  brief to brief.md"*.
- Watch it **iterate**: each step shows the thought, the tool call, and the result;
  a memory scratchpad carries context forward. It writes the file inside the sandbox
  (no shell/exec tool exists — the only filesystem path is `_safe_path`).
- **Production shape:** submit returns `202 + run_id`; the run executes in the
  background and is claimed atomically (one worker per run), heartbeats while alive,
  and is recoverable on crash. See [distributed.md](distributed.md).

### 2. Live Computer-Use — `/browse` (≈1–2 min)

Opens a **real website** in headless Chromium and drives it toward a goal
(`observe → act → repeat`), with a safety boundary that refuses payment/destructive
actions. Contrast with the fixture-based `/qa` module, which runs the same agent
against a bundled sandbox page — same engine, real vs. sandboxed target.

### 3. Deep Research over the real web — `/research` (≈1 min)

DuckDuckGo search + real page fetch/extraction, synthesized into a report that cites
**real source URLs**. Every tool call passes the Tool Gateway (allowlist + audit
log, ADR-005) — the same governance that would wrap real MCP tools. Falls back to a
bundled corpus when the network is unavailable.

## The engineering rigor (why it's more than a demo)

### 4. Text-to-SQL BI Agent — `/text2sql` (≈2 min)

A business question becomes SQL, runs against a sandbox retail DB, and comes back
with an explanation.

- Click an example chip, e.g. *"Top 3 customers by revenue from completed orders"*.
- Watch the **answer**, each **generated SQL** + result, then the **reasoning trace**
  (which model, latency, cost, tool calls).
- **The security story:** every query passes the read-only guards (ADR-004) — single
  SELECT, table allowlist, forced LIMIT + capped OFFSET, read-only connection. Ask
  something destructive ("delete all customers") and the guard rejects it; the agent
  recovers. See `apps/text2sql/tests/test_sql_injection.py`.

### 5. Workflow Orchestrator — `/workflows` (≈1 min)

Predictable, auditable workflows with a human-in-the-loop gate (ADR-007).

- Run the **access_request** workflow. It validates, runs an LLM **risk assessment**,
  then **pauses** at the approval gate — *nothing is granted yet*.
- **Approve** or **Reject**; the decision lands in the **audit log** (who, when, why).

### 6. Observability Console — `/observability` (≈1 min)

Every agent, workflow, and eval run is traced (ADR-006): total runs, success rate,
p95 latency, cost, and a failure taxonomy. Run anything above, refresh here, and the
new trace appears — click a row for the full step-by-step payload.

## What this demonstrates

Not "the model answered" but the full engineering loop around the LLM:
**context → tools → reasoning → action → eval → trace → governance → demo.**
Externally-connected flagships on top; a cost-aware model router, a RAG core with its
own eval lab, guarded SQL, a predictable orchestrator with approval gates, and durable
background runs underneath — all on one service-oriented core.

See `wiki/00_index.md` for the architecture map and the decisions (ADRs) behind each
choice.
