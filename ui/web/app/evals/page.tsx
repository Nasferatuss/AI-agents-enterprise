"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Aggregates = {
  n: number;
  hit_rate: number;
  mrr: number;
  context_precision: number;
  citation_accuracy: number;
  faithfulness: number;
  answer_relevance: number;
};

type RetrievedChunk = {
  chunk: { source: string; text: string };
  score: number;
};

type EvalExample = {
  example_id: string;
  question: string;
  retrieval: { hit: boolean; reciprocal_rank: number; context_precision: number };
  retrieved: RetrievedChunk[];
};

type EvalResult = {
  dataset: string;
  index: string;
  top_k: number;
  judged: boolean;
  created_at: string;
  aggregates: Aggregates;
  examples: EvalExample[];
};

const SAMPLE_DOCS = [
  {
    source: "rag.md",
    text: "RAG grounds a model in retrieved documents before generation.",
  },
  {
    source: "agents.md",
    text: "Agents loop over tool calls under a permission allowlist and audit log.",
  },
  {
    source: "obs.md",
    text: "Observability traces every run with cost and latency.",
  },
];

const METRICS: { key: keyof Aggregates; label: string; color: string }[] = [
  { key: "hit_rate", label: "Hit rate", color: "bg-emerald-500" },
  { key: "mrr", label: "MRR", color: "bg-sky-500" },
  { key: "context_precision", label: "Context precision", color: "bg-violet-500" },
  { key: "citation_accuracy", label: "Citation accuracy", color: "bg-amber-500" },
  { key: "faithfulness", label: "Faithfulness (LLM-judge)", color: "bg-cyan-500" },
  { key: "answer_relevance", label: "Answer relevance", color: "bg-fuchsia-500" },
];

function MetricBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="rounded-lg border border-zinc-800 p-4">
      <div className="flex items-baseline justify-between">
        <p className="text-xs text-zinc-400">{label}</p>
        <p className="font-mono text-sm font-semibold text-zinc-100">
          {value.toFixed(2)}
        </p>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-zinc-800">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function EvalsPage() {
  const [index, setIndex] = useState("kb");
  const [n, setN] = useState(4);
  const [running, setRunning] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsSeed, setNeedsSeed] = useState(false);
  const [seeded, setSeeded] = useState<string | null>(null);
  const [result, setResult] = useState<EvalResult | null>(null);

  async function seed() {
    setSeeding(true);
    setError(null);
    setNeedsSeed(false);
    setSeeded(null);
    try {
      const res = await fetch(
        `${API_URL}/v1/rag/indexes/${encodeURIComponent(index)}/documents`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ documents: SAMPLE_DOCS }),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as {
        documents: number;
        chunks: number;
        index: string;
      };
      setSeeded(
        `Indexed ${data.documents} document${data.documents === 1 ? "" : "s"} · ${data.chunks} chunk${data.chunks === 1 ? "" : "s"} into "${index}".`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSeeding(false);
    }
  }

  async function run() {
    setRunning(true);
    setError(null);
    setNeedsSeed(false);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/v1/evals/rag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index, top_k: 5, synthetic: { n } }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail =
          typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
        if (res.status === 404) {
          setNeedsSeed(true);
        }
        throw new Error(detail);
      }
      setResult((await res.json()) as EvalResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <p className="text-xs text-zinc-500">
        <a href="/" className="hover:text-zinc-300">
          ← workbench
        </a>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Evaluations</h1>
      <p className="mt-1 text-sm text-zinc-400">
        Run a synthetic RAG evaluation against an index and watch the quality
        metrics — retrieval hit rate, MRR, context precision, plus faithfulness,
        answer relevance, and citation accuracy judged by an LLM. Seed a sample
        corpus first if the index is empty.
      </p>

      <section className="mt-8 rounded-lg border border-zinc-800 p-5">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-zinc-500">Index</span>
            <input
              value={index}
              onChange={(e) => setIndex(e.target.value)}
              className="w-40 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm outline-none placeholder:text-zinc-600 focus:border-zinc-600"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-zinc-500">Sample size (n)</span>
            <input
              type="number"
              min={1}
              max={20}
              value={n}
              onChange={(e) =>
                setN(
                  Math.max(1, Math.min(20, Number(e.target.value) || 1)),
                )
              }
              className="w-28 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm outline-none focus:border-zinc-600"
            />
          </label>
          <button
            onClick={seed}
            disabled={seeding || !index.trim()}
            className="rounded-lg border border-zinc-800 px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600 disabled:opacity-40"
          >
            {seeding ? "Seeding…" : "Seed sample corpus"}
          </button>
          <button
            onClick={run}
            disabled={running || !index.trim()}
            className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {running ? "Evaluating…" : "Run evaluation"}
          </button>
        </div>
        {seeded && (
          <p className="mt-3 text-xs text-emerald-400">{seeded}</p>
        )}
      </section>

      {error && (
        <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          <p>{error}</p>
          {needsSeed && (
            <p className="mt-2 text-xs text-red-300/80">
              The index has no documents yet. Click{" "}
              <span className="font-medium">“Seed sample corpus”</span> above to
              populate it, then run the evaluation again.
            </p>
          )}
        </div>
      )}

      {result && (
        <div className="mt-8 space-y-6">
          <section>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-zinc-300">
                Quality metrics
              </h2>
              <div className="flex items-center gap-3 text-xs text-zinc-500">
                <span>
                  dataset{" "}
                  <span className="font-mono text-zinc-400">
                    {result.dataset}
                  </span>
                </span>
                <span>
                  n ={" "}
                  <span className="font-mono text-zinc-300">
                    {result.aggregates.n}
                  </span>
                </span>
                <span
                  className={`rounded px-2 py-0.5 font-mono ${
                    result.judged
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-zinc-700/30 text-zinc-400"
                  }`}
                >
                  {result.judged ? "LLM-judged" : "not judged"}
                </span>
              </div>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {METRICS.map((m) => (
                <MetricBar
                  key={m.key}
                  label={m.label}
                  value={result.aggregates[m.key]}
                  color={m.color}
                />
              ))}
            </div>
          </section>

          <section>
            <h2 className="text-sm font-medium text-zinc-300">
              Examples · {result.examples.length}
            </h2>
            <ul className="mt-3 space-y-2">
              {result.examples.map((ex) => {
                const sources = Array.from(
                  new Set(ex.retrieved.map((r) => r.chunk.source)),
                ).slice(0, 3);
                return (
                  <li
                    key={ex.example_id}
                    className="rounded-lg border border-zinc-800 p-3 text-xs"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-zinc-200">{ex.question}</p>
                      <span
                        className={`shrink-0 font-mono ${
                          ex.retrieval.hit ? "text-emerald-400" : "text-red-400"
                        }`}
                      >
                        {ex.retrieval.hit ? "✓ hit" : "✗ miss"}
                      </span>
                    </div>
                    <p className="mt-1.5 font-mono text-[11px] text-zinc-500">
                      RR {ex.retrieval.reciprocal_rank.toFixed(2)} · ctx-prec{" "}
                      {ex.retrieval.context_precision.toFixed(2)}
                      {sources.length > 0 && (
                        <>
                          {" "}
                          ·{" "}
                          <span className="text-zinc-400">
                            {sources.join(", ")}
                          </span>
                        </>
                      )}
                    </p>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
      )}
    </main>
  );
}
