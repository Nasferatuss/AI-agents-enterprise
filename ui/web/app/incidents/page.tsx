"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Incident = {
  trace_id: string;
  kind: string;
  name: string;
  status: string;
  error: string | null;
  root_cause: string;
};
type Rca = {
  trace_id: string;
  root_cause: string;
  signals: string[];
  summary: string;
  recommendation: string;
};

const CAUSE_COLOR: Record<string, string> = {
  policy_rejection: "text-amber-400",
  loop_no_progress: "text-orange-400",
  provider_unavailable: "text-red-400",
  sql_error: "text-red-400",
  tool_denied: "text-amber-400",
  scenario_failures: "text-red-400",
  low_eval_quality: "text-orange-400",
  unknown: "text-zinc-400",
};

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [rca, setRca] = useState<Rca | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      const r = await fetch(`${API_URL}/v1/apps/incidents`).then((x) => x.json());
      setIncidents(r as Incident[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function analyze(id: string) {
    const r = await fetch(`${API_URL}/v1/apps/incidents/${id}/rca`, {
      method: "POST",
    }).then((x) => x.json());
    setRca(r as Rca);
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <p className="text-xs text-zinc-500">
        <a href="/" className="hover:text-zinc-300">
          ← workbench
        </a>
      </p>
      <div className="mt-2 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          Incident Response
        </h1>
        <button
          onClick={refresh}
          className="rounded-lg border border-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-600"
        >
          ↻ refresh
        </button>
      </div>
      <p className="mt-1 text-sm text-zinc-400">
        Failed runs from the trace store, with a deterministic root cause. Click
        one for the RCA report. Closes the loop with observability.
      </p>

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      <section className="mt-8 overflow-hidden rounded-lg border border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-900 text-xs text-zinc-500">
            <tr>
              <th className="px-3 py-2 font-medium">run</th>
              <th className="px-3 py-2 font-medium">status</th>
              <th className="px-3 py-2 font-medium">root cause</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((i) => (
              <tr key={i.trace_id} className="border-t border-zinc-800/60">
                <td className="px-3 py-2 text-zinc-200">{i.name}</td>
                <td className="px-3 py-2 font-mono text-xs text-red-400">
                  {i.status}
                </td>
                <td className={`px-3 py-2 font-mono text-xs ${CAUSE_COLOR[i.root_cause]}`}>
                  {i.root_cause}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => analyze(i.trace_id)}
                    className="rounded border border-zinc-700 px-2 py-0.5 text-xs text-zinc-300 hover:border-zinc-500"
                  >
                    RCA
                  </button>
                </td>
              </tr>
            ))}
            {incidents.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-xs text-zinc-600">
                  No failed runs. Run <code>make seed</code> or trigger a failure.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {rca && (
        <section className="mt-6 rounded-lg border border-zinc-700 bg-zinc-900/40 p-5">
          <h2 className="text-sm font-medium text-zinc-200">
            RCA ·{" "}
            <span className={`font-mono ${CAUSE_COLOR[rca.root_cause]}`}>
              {rca.root_cause}
            </span>
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-300">
            {rca.signals.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
          {rca.summary && (
            <p className="mt-3 text-sm text-zinc-300">{rca.summary}</p>
          )}
          {rca.recommendation && (
            <p className="mt-2 rounded bg-emerald-500/10 p-3 text-sm text-emerald-300">
              Fix: {rca.recommendation}
            </p>
          )}
          {!rca.summary && (
            <p className="mt-3 text-xs text-zinc-500">
              (LLM narrative unavailable — configure a provider for the written
              RCA; the root cause above is deterministic.)
            </p>
          )}
        </section>
      )}
    </main>
  );
}
