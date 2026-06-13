"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type TraceSummary = {
  id: string;
  kind: string;
  name: string;
  status: string;
  created_at: string;
  latency_ms: number;
  cost_usd: number | null;
  input_tokens: number;
  output_tokens: number;
  num_steps: number;
  error: string | null;
};

type FailureBucket = { kind: string; status: string; count: number };
type Aggregates = {
  total: number;
  success_rate: number;
  total_cost_usd: number;
  p95_latency_ms: number;
  by_kind: Record<string, number>;
  failures: FailureBucket[];
};

type TraceDetail = TraceSummary & { payload: Record<string, unknown> };

const KIND_COLOR: Record<string, string> = {
  agent: "text-sky-400",
  workflow: "text-violet-400",
  eval: "text-amber-400",
};

function StatusDot({ status }: { status: string }) {
  const ok = status === "completed";
  const warn = status === "awaiting_approval";
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-emerald-400" : warn ? "bg-amber-400" : "bg-red-400"}`}
    />
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 p-4">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-zinc-100">{value}</p>
    </div>
  );
}

export default function ObservabilityPage() {
  const [agg, setAgg] = useState<Aggregates | null>(null);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      const [a, t] = await Promise.all([
        fetch(`${API_URL}/v1/observability/summary`).then((r) => r.json()),
        fetch(`${API_URL}/v1/observability/traces`).then((r) => r.json()),
      ]);
      setAgg(a as Aggregates);
      setTraces(t as TraceSummary[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function open(id: string) {
    const d = await fetch(`${API_URL}/v1/observability/traces/${id}`).then((r) =>
      r.json(),
    );
    setDetail(d as TraceDetail);
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <p className="text-xs text-zinc-500">
        <a href="/" className="hover:text-zinc-300">
          ← workbench
        </a>
      </p>
      <div className="mt-2 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          Observability Console
        </h1>
        <button
          onClick={refresh}
          className="rounded-lg border border-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-600"
        >
          ↻ refresh
        </button>
      </div>
      <p className="mt-1 text-sm text-zinc-400">
        Every agent / workflow / eval run is traced (ADR-006). Cost, latency,
        and failure taxonomy across the platform.
      </p>

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          gateway unreachable: {error}
        </p>
      )}

      {agg && (
        <section className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Total runs" value={String(agg.total)} />
          <Stat
            label="Success rate"
            value={`${Math.round(agg.success_rate * 100)}%`}
          />
          <Stat label="p95 latency" value={`${agg.p95_latency_ms} ms`} />
          <Stat label="Total cost" value={`$${agg.total_cost_usd.toFixed(4)}`} />
        </section>
      )}

      {agg && agg.failures.length > 0 && (
        <section className="mt-4 rounded-lg border border-zinc-800 p-4">
          <h2 className="text-sm font-medium text-zinc-300">Failure taxonomy</h2>
          <ul className="mt-2 flex flex-wrap gap-2">
            {agg.failures.map((f, i) => (
              <li
                key={i}
                className="rounded-full bg-red-500/10 px-3 py-1 font-mono text-xs text-red-400"
              >
                {f.kind}/{f.status} · {f.count}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-6 overflow-hidden rounded-lg border border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-900 text-xs text-zinc-500">
            <tr>
              <th className="px-3 py-2 font-medium">kind</th>
              <th className="px-3 py-2 font-medium">name</th>
              <th className="px-3 py-2 font-medium">status</th>
              <th className="px-3 py-2 font-medium">steps</th>
              <th className="px-3 py-2 font-medium">latency</th>
              <th className="px-3 py-2 font-medium">cost</th>
            </tr>
          </thead>
          <tbody>
            {traces.map((t) => (
              <tr
                key={t.id}
                onClick={() => open(t.id)}
                className="cursor-pointer border-t border-zinc-800/60 hover:bg-zinc-900/50"
              >
                <td
                  className={`px-3 py-2 font-mono text-xs ${KIND_COLOR[t.kind] ?? "text-zinc-400"}`}
                >
                  {t.kind}
                </td>
                <td className="px-3 py-2 text-zinc-200">{t.name}</td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
                    <StatusDot status={t.status} />
                    {t.status}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs text-zinc-400">
                  {t.num_steps}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-zinc-400">
                  {t.latency_ms}ms
                </td>
                <td className="px-3 py-2 font-mono text-xs text-zinc-400">
                  {t.cost_usd != null ? `$${t.cost_usd.toFixed(5)}` : "—"}
                </td>
              </tr>
            ))}
            {traces.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-xs text-zinc-600">
                  No traces yet — run an agent, workflow, or eval.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {detail && (
        <section className="mt-6 rounded-lg border border-zinc-700 bg-zinc-900/40 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-200">
              Trace{" "}
              <span className="font-mono text-zinc-500">{detail.id}</span> ·{" "}
              <span className={KIND_COLOR[detail.kind]}>{detail.kind}</span>/
              {detail.name}
            </h2>
            <button
              onClick={() => setDetail(null)}
              className="text-xs text-zinc-500 hover:text-zinc-300"
            >
              close ✕
            </button>
          </div>
          {detail.error && (
            <p className="mt-2 text-xs text-red-400">error: {detail.error}</p>
          )}
          <pre className="mt-3 max-h-96 overflow-auto rounded bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-300">
            {JSON.stringify(detail.payload, null, 2)}
          </pre>
        </section>
      )}
    </main>
  );
}
