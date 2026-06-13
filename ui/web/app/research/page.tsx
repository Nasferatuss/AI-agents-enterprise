"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const EXAMPLES = [
  "How do you build reliable AI agents?",
  "What makes a RAG system trustworthy?",
  "How is cost controlled when routing LLM calls?",
];

type Source = { n: number; url: string; title: string };
type ToolCall = {
  tool: string;
  args: Record<string, unknown>;
  allowed: boolean;
  error: string | null;
  latency_ms: number;
};
type Report = {
  question: string;
  sub_questions: string[];
  sources: Source[];
  report: string;
  tool_calls: ToolCall[];
  provider: string;
  model: string;
};

export default function ResearchPage() {
  const [q, setQ] = useState(EXAMPLES[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);

  async function run(question: string) {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await fetch(`${API_URL}/v1/apps/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) {
        const b = await res.json().catch(() => null);
        throw new Error(b?.detail ?? `HTTP ${res.status}`);
      }
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
        Deep Research Agent
      </h1>
      <p className="mt-1 text-sm text-zinc-400">
        Plan → research through the governed Tool Gateway → cited report. Every
        tool call passes an allowlist and is audited (ADR-005).
      </p>

      <form
        className="mt-6 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) run(q.trim());
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm outline-none focus:border-zinc-600"
        />
        <button
          type="submit"
          disabled={loading || !q.trim()}
          className="rounded-lg bg-teal-600 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "Researching…" : "Research"}
        </button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setQ(ex);
              run(ex);
            }}
            className="rounded-full border border-zinc-800 px-3 py-1 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
          >
            {ex}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      {report && (
        <div className="mt-8 space-y-5">
          <section className="rounded-lg border border-zinc-800 p-5">
            <h2 className="text-sm font-medium text-zinc-300">Report</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-100">
              {report.report}
            </p>
          </section>

          <section>
            <h2 className="text-sm font-medium text-zinc-300">Sources</h2>
            <ol className="mt-2 space-y-1">
              {report.sources.map((s) => (
                <li key={s.n} className="text-sm text-zinc-300">
                  <span className="font-mono text-xs text-zinc-500">[{s.n}]</span>{" "}
                  {s.title}{" "}
                  <span className="font-mono text-xs text-teal-400">{s.url}</span>
                </li>
              ))}
            </ol>
          </section>

          <section>
            <h2 className="text-sm font-medium text-zinc-300">
              Tool calls{" "}
              <span className="text-zinc-600">(gateway audit log)</span>
            </h2>
            <ul className="mt-2 space-y-1">
              {report.tool_calls.map((c, i) => (
                <li key={i} className="font-mono text-xs text-zinc-400">
                  <span
                    className={c.allowed ? "text-emerald-400" : "text-red-400"}
                  >
                    {c.allowed ? "✓" : "✕"}
                  </span>{" "}
                  {c.tool}({JSON.stringify(c.args).slice(0, 60)}) · {c.latency_ms}ms
                  {c.error ? ` · ${c.error}` : ""}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </main>
  );
}
