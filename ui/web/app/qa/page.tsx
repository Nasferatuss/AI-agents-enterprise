"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Element = { id: string; kind: string; label: string; value: string };
type Screen = { state: string; elements: Element[]; error: string | null };
type StepResult = { description: string; passed: boolean; detail: string };
type ScenarioResult = {
  name: string;
  description: string;
  passed: boolean;
  steps: StepResult[];
};
type Bug = { scenario: string; expected: string; actual: string };
type Report = {
  scenarios: ScenarioResult[];
  bugs: Bug[];
  passed: number;
  failed: number;
  action_trace: { tool: string; args: Record<string, unknown> }[];
  summary: string;
};

export default function QaPage() {
  const [screen, setScreen] = useState<Screen | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/v1/apps/cua/screen`)
      .then((r) => r.json())
      .then((s) => setScreen(s as Screen))
      .catch((e) => setError(String(e)));
  }, []);

  async function run() {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await fetch(`${API_URL}/v1/apps/cua/run`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setReport((await res.json()) as Report);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <p className="text-xs text-zinc-500">
        <a href="/" className="hover:text-zinc-300">
          ← workbench
        </a>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        Guarded Computer-Use QA
      </h1>
      <p className="mt-1 text-sm text-zinc-400">
        A QA agent drives a legacy UI sandbox through a guarded action space
        (observe / click / type — allowlisted & audited) and writes a bug report.
      </p>

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      <section className="mt-8 grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-zinc-800 p-4">
          <h2 className="text-sm font-medium text-zinc-300">
            Legacy UI sandbox{" "}
            {screen && <span className="text-zinc-600">· {screen.state}</span>}
          </h2>
          {/* a deliberately dated "legacy" form rendering */}
          <div className="mt-3 rounded border border-zinc-700 bg-zinc-200 p-4 font-mono text-xs text-zinc-800">
            {screen?.elements.map((e) =>
              e.kind === "button" ? (
                <button
                  key={e.id}
                  className="mr-2 mt-1 rounded-sm border border-zinc-500 bg-zinc-300 px-2 py-0.5"
                >
                  {e.label}
                </button>
              ) : e.kind === "input" ? (
                <div key={e.id} className="mt-1">
                  {e.label}:{" "}
                  <span className="inline-block w-32 border-b border-zinc-500">
                    {e.value || " "}
                  </span>
                </div>
              ) : (
                <div key={e.id} className="mt-1 font-semibold">
                  {e.label}
                </div>
              ),
            )}
          </div>
        </div>

        <div className="flex flex-col justify-center rounded-lg border border-zinc-800 p-4">
          <p className="text-sm text-zinc-400">
            Run the scenario suite against the sandbox. Two bugs are planted —
            see if the agent finds them.
          </p>
          <button
            onClick={run}
            disabled={loading}
            className="mt-3 w-fit rounded-lg bg-zinc-100 px-5 py-2 text-sm font-medium text-zinc-900 disabled:opacity-40"
          >
            {loading ? "Running…" : "Run QA scenarios"}
          </button>
        </div>
      </section>

      {report && (
        <div className="mt-8 space-y-5">
          <section className="flex items-center gap-4">
            <span className="rounded-lg bg-emerald-500/15 px-3 py-1 text-sm text-emerald-400">
              {report.passed} passed
            </span>
            <span className="rounded-lg bg-red-500/15 px-3 py-1 text-sm text-red-400">
              {report.failed} failed
            </span>
            <span className="text-xs text-zinc-500">
              {report.action_trace.length} guarded actions
            </span>
          </section>

          <section>
            <h2 className="text-sm font-medium text-zinc-300">Scenarios</h2>
            <ul className="mt-2 space-y-1">
              {report.scenarios.map((s) => (
                <li key={s.name} className="text-sm">
                  <span className={s.passed ? "text-emerald-400" : "text-red-400"}>
                    {s.passed ? "✓" : "✕"}
                  </span>{" "}
                  <span className="text-zinc-200">{s.name}</span>{" "}
                  <span className="text-zinc-500">— {s.description}</span>
                </li>
              ))}
            </ul>
          </section>

          {report.bugs.length > 0 && (
            <section className="rounded-lg border border-red-500/30 bg-red-500/5 p-4">
              <h2 className="text-sm font-medium text-red-300">
                Bug report · {report.bugs.length} found
              </h2>
              {report.summary && (
                <p className="mt-2 text-sm text-zinc-300">{report.summary}</p>
              )}
              <ul className="mt-2 space-y-1.5 text-sm text-zinc-300">
                {report.bugs.map((b, i) => (
                  <li key={i}>
                    <span className="font-mono text-xs text-red-400">
                      [{b.scenario}]
                    </span>{" "}
                    expected {b.expected}; got {b.actual}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </main>
  );
}
