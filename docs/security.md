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
  settings, never from request data — no user-controlled SSRF. The optional MCP
  server (`WB_MCP_SERVER_COMMAND`) is likewise a config-controlled command, not
  request-derived; tools it exposes are registered behind the **same gateway
  allowlist + audit log** (ADR-005) as the in-process connectors.
- **Trace payloads** scrub raw DB rows from `run_sql` results (keep sql/columns/
  row_count) so traces don't duplicate sensitive query data.
- **Trace queries** use SQLAlchemy bound parameters — no SQL injection.

### MCP subprocess (`WB_MCP_SERVER_COMMAND`)

When set, the deep-research agent sources its tools from a real MCP server: the
value is `shlex.split` and spawned as a **child process over stdio**
(`apps/deep_research/.../api.py`). This is a legitimate feature — it lets the
agent use tools from an external MCP server instead of the in-process corpus
connectors — but it means **whoever controls `.env` controls a command the API
process will execute** (RCE on `.env` compromise).

Mitigations / operating rules:

- `.env` must be treated as a secret: never committed (it is git-ignored), and
  readable only by the service account. Compromise of `.env` is already game-over
  for API keys; this widens it to code execution, so the same protection applies.
- It is **unset by default** — no subprocess is spawned unless explicitly
  configured.
- In production, **pin** the command to a known, audited binary/module and do not
  derive it from anything request- or operator-supplied at runtime; ideally
  validate it against an allowlist before launch. The tools the server exposes
  still pass through the same gateway allowlist + audit log (ADR-005).

### Transport & access

CORS restricted to the console origin and the methods/headers it uses. Input
length caps on `question` / `input` / `actor` bound LLM token cost and
audit-log poisoning.

**Optional API auth & rate limiting** (off by default so the local demo is open;
enabled purely from config):
- `WB_API_KEY` → every `/v1/*` request must carry a matching `X-API-Key` header.
- `WB_RATE_LIMIT_PER_MIN` → caps `POST /v1/*` per client IP per minute.

## Known limitations (hardening backlog)

| Gap | Status / risk |
|-----|---------------|
| API auth & rate limiting | ✅ available, **off by default** — set `WB_API_KEY` / `WB_RATE_LIMIT_PER_MIN` before exposing to a network. Rate limiter is per-process; multi-instance needs Redis. |
| **Approval `actor` is self-attested** unless `WB_APPROVAL_TOKEN` set | Audit identity unverifiable without real auth — add a role check (`require_approver_role`) for production. |
| `GET /v1/models` exposes provider topology | Fingerprinting only — put behind `WB_API_KEY` in production. |
| `WB_MCP_SERVER_COMMAND` runs an env-controlled subprocess | RCE if `.env` is compromised. Unset by default; pin/validate the command in production (see [MCP subprocess](#mcp-subprocess-wb_mcp_server_command)). |

For an internet-exposed deployment: set `WB_API_KEY`, `WB_RATE_LIMIT_PER_MIN`,
and `WB_CORS_ORIGINS`, and front the service with TLS (see `docs/deploy.md`).

## Hardening 2026-06-20

Findings closed in this pass (all ship with regression tests):

- **SSRF guard** (`platform/shared/.../netguard.py`): `assert_public_url` /
  `safe_get` reject non-`http(s)` schemes and private/loopback/link-local/metadata
  (169.254.169.254) targets, re-validating every redirect hop. Wired into the
  autonomous `fetch_url`, deep-research fetch, and live-browse navigate/start-url.
- **File-sandbox symlink escape**: `_safe_path` now enforces realpath containment
  and refuses a final symlink, on top of the existing `..`-traversal / absolute-path
  checks.
- **Live-browse sensitive-input block**: typing into a card/CVV/password/PAN field
  marks the session and blocks any subsequent submit/click — closes the
  type-then-Continue bypass.
- **Prod fail-fast auth**: in `WB_ENV=prod` the gateway refuses to start when
  `WB_API_KEY` / `WB_APPROVAL_TOKEN` are unset or CORS is wildcard.
- **Security headers**: gateway adds `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`.
- **Durable audit sink**: ToolGateway gained an optional persistent `audit_sink`
  (denied calls included) so the audit trail outlives a per-request gateway.
- **AST depth limit**: the demo `_safe_eval` caps AST depth to prevent a
  `RecursionError` DoS.
- **Postgres password parameterized**: `docker-compose.yml` reads
  `WB_PG_PASSWORD` (default `workbench` for the local demo); override in any
  non-local environment.

## Running the security QA

```bash
make qa                                  # lint + full suite (incl. injection + regression)
uv run pytest apps/text2sql/tests/test_sql_injection.py -q   # adversarial SQL only
```
