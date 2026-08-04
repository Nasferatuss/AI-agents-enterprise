# Security policy

This platform lets a language model generate and execute SQL, drive a real
browser, and call tools. The guard rails around that are the substance of the
project, so a hole in one of them is worth reporting properly.

The full threat model, the implemented controls and the known limitations are in
**[docs/security.md](docs/security.md)**. Please read it before reporting — it
already states what is deliberately out of scope, and most of the obvious
questions are answered there.

## Reporting

Use **[Report a vulnerability](https://github.com/Nasferatuss/AI-agents-enterprise/security/advisories/new)**
(GitHub private vulnerability reporting), not a public issue.

Include the commit, how the platform was running (local, Compose, which
providers), and a reproduction. For a guard bypass, the exact input that gets
through is the whole report.

Single maintainer, no bug bounty. Expect a first response within a week; if
nothing arrives in two, ping the issue tracker without details. Please allow a
reasonable window before publishing, and say if you would like credit.

## Especially interesting

These are the places where a finding actually matters:

- **A SQL guard bypass** — `platform/capabilities/sql_guard.py`. Anything that
  reaches a write, DDL, an unallowlisted table, or a filesystem/code-loading
  function through the parser layer. The adversarial suite is
  `tests/test_sql_injection.py`; a case it does not cover is a good report.
- **Skipping the approval gate** — `platform/orchestrator/engine.py`. Any way a
  `requires_approval` step executes without a recorded human decision.
- **Prompt injection that turns into a real action.** Model output deciding
  control flow, or tool-result content escaping into a privileged position. This
  is the platform's primary in-scope threat.
- **SSRF** — an outbound request target derived from request data rather than
  `WB_*` settings.
- **Escaping the computer-use safety boundary** — the browser flagship refusing
  payment and destructive actions, and getting it to do one anyway.
- **Secret leakage** — a key, DSN credential or raw row set appearing in a trace,
  a log or an error response.

## Out of scope

- The limitations already documented in
  [docs/security.md](docs/security.md#known-limitations). Restating one is not a
  finding; **breaking out of** one is.
- Anything that assumes the attacker already controls `WB_*` environment
  settings or the config. Configuration is trusted input.
- Denial of service by volume, and cost abuse on a deployment left open to the
  internet without auth in front of it. The platform is documented as a
  reference/demo deployment, not a hardened multi-tenant service.
- Vulnerabilities in third-party dependencies with no exploitable path here —
  please report those upstream. If there *is* a path here, that is in scope.
- Findings against the bundled fixtures and sample data.

## Supported versions

Only `main`. Fixes land there and are not backported.
