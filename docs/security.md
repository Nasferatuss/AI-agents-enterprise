# Security model & QA (Phase 4)

Threat model, controls, and known limitations for the MVP. Backed by an
adversarial test suite and an independent security review (June 2026).

## Threat model

This is a **portfolio/demo** platform, normally run locally or on a single VPS
for a public demo. The relevant adversaries:

- A **jailbroken / prompt-injected model** emitting a dangerous tool call
  (destructive SQL, file reads). This is the primary in-scope threat — agents
  generate and execute SQL, and tool results feed back into the model.
- An **untrusted network caller** reaching the gateway port (cost abuse,
  reading traces). Partly in scope; see Known limitations.

## Controls (implemented & tested)

### Read-only SQL execution (ADR-004) — `apps/text2sql/safe_sql.py`

Defense in depth; every layer is exercised by `tests/test_sql_injection.py`:

1. **Parser validation** (sqlglot): exactly one statement; only `SELECT` / CTE /
   `UNION`; **any** write/DDL/admin node anywhere in the tree is rejected
   (catches data-modifying CTEs like `WITH x AS (DELETE …) SELECT …`).
   Un-tokenizable input becomes a clean rejection, never a leaked exception.
2. **Function denylist**: filesystem/code-loading functions that take no table
   argument (`load_extension`, `pg_read_file`, `lo_import`, `pg_ls_dir`, …) —
   the table allowlist alone is blind to these.
3. **Table allowlist**: every referenced table (incl. in subqueries and UNIONs)
   must be allowlisted; CTE names are exempt.
4. **Forced `LIMIT`**: injected when absent, capped at 200.
5. **Read-only connection**: SQLite opened `mode=ro` (OS-level); for Postgres,
   point the BI DSN at a **read-only DB user** in a sandbox DB. This is the real
   boundary — the parser guard is defense-in-depth.

The agent treats a rejected query as a normal tool error and recovers.

### Workflow approval gate (ADR-007) — `platform/orchestrator/engine.py`

Control flow is fully deterministic — no LLM output decides which step runs.
A `requires_approval` step suspends *before* executing; the risky action never
runs without a human decision, which is recorded in an audit log. An optional
shared-secret gate (`WB_APPROVAL_TOKEN` → `X-Approval-Token` header) protects
approve/reject when configured.

### Secrets, SSRF, trace store

- **API keys** are read from env at call time and never logged; the trace-store
  URL is logged with credentials stripped.
- **Outbound request targets** (providers, Ollama, Qdrant) come only from `WB_*`
  settings, never from request data — no user-controlled SSRF.
- **Trace payloads** scrub raw DB rows from `run_sql` results (keep sql/columns/
  row_count) so traces don't duplicate sensitive query data.
- **Trace queries** use SQLAlchemy bound parameters — no SQL injection.

### Transport

CORS restricted to the console origin and the methods/headers it uses. Input
length caps on `question` / `input` / `actor` bound LLM token cost and
audit-log poisoning.

## Known limitations (out of scope for the MVP; hardening backlog)

Documented honestly rather than hidden — these are the gaps a reviewer should
know about before exposing the service to an untrusted network:

| Gap | Risk | Planned fix |
|-----|------|-------------|
| **No API authentication** on the gateway | Anyone reaching the port can run agents (LLM cost) and read traces | `X-API-Key` dependency from env; per-route auth |
| **No rate limiting** on cost-generating endpoints | Request-loop can deplete API credits | `slowapi` global IP limit on `/v1/chat`, `/run`, `/ask`, `/evals` |
| **Approval `actor` is self-attested** unless `WB_APPROVAL_TOKEN` set | Audit identity unverifiable | Real auth + role check (`require_approver_role`) |
| `GET /v1/models` exposes provider topology | Fingerprinting | Put behind auth in production |

These are appropriate to defer for a local demo but **must** be closed before any
multi-user or internet-exposed deployment (Phase 6 hardening).

## Running the security QA

```bash
make qa                                  # lint + full suite (incl. injection + regression)
uv run pytest apps/text2sql/tests/test_sql_injection.py -q   # adversarial SQL only
```
