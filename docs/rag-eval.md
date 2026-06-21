# RAG retrieval evaluation — report

Measured retrieval quality of the RAG core (chunking → embeddings → Qdrant → hybrid
RRF search), and the regression gate that keeps it from silently degrading. These
numbers are **deterministic and network-free**: the `HashEmbedder` (a non-semantic,
reproducible embedding) plus an in-memory Qdrant, so the same input always gives the
same score and the gate can run in CI without a GPU or API keys.

## Methodology

**Dataset.** A golden knowledge base, `examples/rag/knowledge_base.json`: 6 documents
(RAG, agents, observability, evaluation, routing, governance) and 6 questions, each with
exactly one relevant source document. Small on purpose — it is a *regression* fixture
(catch "the right doc stopped being retrieved"), not a leaderboard.

**Pipeline.** Each document is chunked (heading-aware) and embedded; queries run through
the same hybrid search the product uses — dense vectors + lexical BM25, fused with
Reciprocal Rank Fusion (RRF). `platform/rag/`.

**Metrics** (all LLM-free, `platform/evals/metrics.py`):

- **hit_rate** — fraction of questions whose relevant doc appears in the top-k.
- **MRR** — mean reciprocal rank of the first relevant hit (1.0 = always rank 1).
- **context_precision** — fraction of retrieved chunks that are relevant. With exactly
  one relevant chunk per question, this is bounded by `1/k` — so it *measures crowding*
  (how much irrelevant context the prompt carries), not a defect.

## Results

Golden KB, `HashEmbedder` + hybrid RRF, measured 2026-06-21 (reproducible):

| top_k | hit_rate | MRR | context_precision | note |
|---|---|---|---|---|
| 1 | 1.000 | 1.000 | 1.000 | the single relevant doc is retrieved at rank 1 every time |
| 3 | 1.000 | 1.000 | 0.333 | still rank 1 (MRR=1.0); precision = 1/3 = the single-relevant ceiling |
| 5 | 1.000 | 1.000 | 0.200 | precision = 1/5 ceiling; recall unaffected |

**Read of the result:** even with a *non-semantic* hash embedding, hybrid RRF puts the
correct document at **rank 1 for all 6 questions** (MRR = 1.0) — the lexical signal
carries this corpus. `context_precision` falling as `1/k` is arithmetic, not regression:
more retrieved chunks dilute precision when only one is relevant, which is why the gate
floors it rather than targeting it. With real semantic embeddings (Ollama
`nomic-embed-text` on the GPU box) the same harness would be run against a larger, harder
set where dense retrieval starts to matter.

## The regression gate (CI)

`tests/test_eval_regression.py` runs this eval on every CI run and fails the build if
retrieval drops below a baseline floor (`top_k=3`):

| metric | floor | measured | headroom |
|---|---|---|---|
| hit_rate | ≥ 0.80 | 1.000 | +0.20 |
| MRR | ≥ 0.70 | 1.000 | +0.30 |
| context_precision | ≥ 0.30 | 0.333 | +0.033 |

The floors are a *regression* baseline, not a quality target — they catch a chunking,
embedding, or fusion change that silently degrades retrieval, before it ships.

## What this does and doesn't cover

- **Covered, deterministic:** retrieval quality (recall/MRR/precision) — no LLM, runs in CI.
- **Not covered here:** answer **faithfulness** and **citation accuracy**, which need an
  LLM judge (`platform/evals/judge.py`) and therefore a provider. Those run as a separate
  live eval (`workbench_evals.runner.run_eval`) and are intentionally out of the CI gate so
  the gate stays network-free and reproducible. The harness for them exists; the published
  numbers above are the deterministic slice.

## Reproduce

```bash
uv run pytest tests/test_eval_regression.py -q        # the CI gate
# the table above is produced by run_retrieval_regression at top_k 1/3/5 on the golden KB
```
