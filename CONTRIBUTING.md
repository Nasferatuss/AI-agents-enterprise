# Contributing to the Agent Workbench

Thanks for looking. This is a reference platform, which shapes what a good
change looks like here: the point is not only that a feature works, but that a
reader can see *how* it is engineered. A PR that adds capability and leaves no
trace of evaluation, tracing or a test is usually not finished.

## Setup

```bash
make install          # uv sync + UI deps
make qa               # lint + the full test suite — the gate CI enforces
```

Needs Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22 and Docker (for
the Compose stack). `make help` lists every target.

To run the thing:

```bash
make up               # infra + API via Docker Compose
make ui               # Next.js demo console on :3000
make seed             # sample runs, so /observability has something to show
```

## Tests stay network-free

The suite is ~300 tests and **none of them touch the network**. That is a
property worth protecting: it is why CI is fast, deterministic, and honest about
what it proves.

- New tests use fixtures and fakes. If a test needs a provider, fake the
  provider.
- Live-network paths (`WB_RESEARCH_LIVE_WEB`, `bench-live`, the real-browser
  Playwright suite) are opt-in and marked. The browser e2e runs in CI under its
  own job with a bundled sandbox UI — a real browser, not a real website.
- `make eval-regression` is a gate, not a report: retrieval quality is asserted,
  so a change that quietly degrades RAG fails the build.

## What a good PR looks like

- **One concern per PR.** Large changes need an issue first — a 200-file PR does
  not get reviewed, it gets closed.
- **Say what breaks if it is wrong.** The commit body is where the reasoning
  goes: the alternative you rejected, the thing you are unsure about. "Fix bug"
  tells a future reader nothing.
- **Tests that would have failed before the change.**
- **`make qa` is green.** Ruff lint, ruff format, the full suite.
- **New behaviour is observable.** Anything that performs a run should emit a
  trace — cost, latency and outcome — like the rest of the platform. An agent
  action that cannot be inspected afterwards does not match the platform it
  lives in.
- **Be honest in the README.** The repository distinguishes production-grade
  engineering from scoped demo seams, in
  [What's real vs demo](README.md#whats-real-vs-demo). If your change is a demo
  seam, put it there. Overclaiming costs more than the feature is worth.
- **If you used an AI assistant, say so in the PR description** and confirm you
  have read and tested the result yourself. Assisted code is welcome; unreviewed
  generated code is not.

## Where things live

| Path | What it is |
|---|---|
| `platform/` | The core: model router, agent runtime, context engine, RAG, evals, workflow orchestrator, observability |
| `apps/` | Demo modules and the flagship agents |
| `ui/web/` | Next.js demo console |
| `infra/` | Compose stack, migrations |
| `tests/` | The network-free suite plus the marked live/browser ones |
| `docs/` | Architecture, security model, benchmarks, demo script |

New capability usually belongs in `platform/` with a thin module in `apps/`
demonstrating it — not the other way round.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## Licence

MIT — see [LICENSE](LICENSE). By contributing you agree your work ships under it.
