"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type SqlCall = {
  sql: string;
  columns: string[];
  rows: (string | number | null)[][];
  row_count: number;
  is_error: boolean;
  error?: string | null;
};

type StepOutput = {
  text: string;
  provider: string;
  model: string;
  latency_ms: number;
  cost_usd: number | null;
  tool_calls: { id: string; name: string; arguments: Record<string, unknown> }[];
};

type AgentStep = {
  output: StepOutput;
  tool_executions: {
    name: string;
    arguments: Record<string, unknown>;
    result: string;
    is_error: boolean;
  }[];
};

type AskResponse = {
  answer: string;
  sql_calls: SqlCall[];
  run: {
    status: string;
    usage: { input_tokens: number; output_tokens: number };
    cost_usd: number | null;
    steps: AgentStep[];
  };
};

const EXAMPLES = [
  "Top 3 customers by revenue from completed orders",
  "Monthly revenue for 2026 by product category",
  "How many orders are pending right now?",
];

function Sql({ sql }: { sql: string }) {
  return (
    <pre className="overflow-x-auto rounded bg-zinc-900 p-3 font-mono text-xs leading-relaxed text-emerald-300">
      {sql}
    </pre>
  );
}

function ResultTable({ call }: { call: SqlCall }) {
  if (call.is_error) {
    return (
      <p className="rounded bg-red-500/10 p-3 text-xs text-red-400">
        rejected: {call.error}
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded border border-zinc-800">
      <table className="w-full text-left text-xs">
        <thead className="bg-zinc-900 text-zinc-400">
          <tr>
            {call.columns.map((c) => (
              <th key={c} className="px-3 py-2 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {call.rows.map((row, i) => (
            <tr key={i} className="border-t border-zinc-800/60">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-1.5 font-mono text-zinc-300">
                  {cell === null ? "∅" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-zinc-800 px-3 py-1.5 text-[11px] text-zinc-500">
        {call.row_count} row{call.row_count === 1 ? "" : "s"}
      </p>
    </div>
  );
}

function Trace({ steps }: { steps: AgentStep[] }) {
  return (
    <details className="rounded-lg border border-zinc-800 p-4">
      <summary className="cursor-pointer text-sm font-medium text-zinc-300">
        Reasoning trace · {steps.length} step{steps.length === 1 ? "" : "s"}
      </summary>
      <ol className="mt-3 space-y-3">
        {steps.map((step, i) => (
          <li key={i} className="rounded bg-zinc-900/60 p-3 text-xs">
            <p className="mb-1 font-mono text-[11px] text-zinc-500">
              step {i + 1} · {step.output.provider}/{step.output.model} ·{" "}
              {step.output.latency_ms}ms
              {step.output.cost_usd != null &&
                ` · $${step.output.cost_usd.toFixed(5)}`}
            </p>
            {step.output.text && (
              <p className="text-zinc-300">{step.output.text}</p>
            )}
            {step.tool_executions.map((ex, j) => (
              <p key={j} className="mt-1 font-mono text-[11px] text-zinc-400">
                → {ex.name}({JSON.stringify(ex.arguments).slice(0, 120)}){" "}
                <span className={ex.is_error ? "text-red-400" : "text-emerald-400"}>
                  {ex.is_error ? "error" : "ok"}
                </span>
              </p>
            ))}
          </li>
        ))}
      </ol>
    </details>
  );
}

export default function Text2SqlPage() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);

  async function ask(q: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/v1/apps/text2sql/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setResult((await res.json()) as AskResponse);
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
        Text-to-SQL BI Agent
      </h1>
      <p className="mt-1 text-sm text-zinc-400">
        Business question → SQL → result → explanation. Read-only guards per
        ADR-004.
      </p>

      <form
        className="mt-8 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) ask(question.trim());
        }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Top 3 customers by revenue…"
          className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm outline-none placeholder:text-zinc-600 focus:border-zinc-600"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "Running…" : "Ask"}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setQuestion(ex);
              ask(ex);
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

      {result && (
        <div className="mt-8 space-y-5">
          <section className="rounded-lg border border-zinc-800 p-4">
            <h2 className="text-sm font-medium text-zinc-300">Answer</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-100">
              {result.answer || "(agent hit max steps)"}
            </p>
            <p className="mt-3 text-[11px] text-zinc-500">
              {result.run.usage.input_tokens + result.run.usage.output_tokens}{" "}
              tokens
              {result.run.cost_usd != null &&
                ` · $${result.run.cost_usd.toFixed(5)}`}{" "}
              · {result.run.status}
            </p>
          </section>

          {result.sql_calls.map((call, i) => (
            <section key={i} className="space-y-2">
              <h2 className="text-sm font-medium text-zinc-300">
                SQL #{i + 1}
              </h2>
              <Sql sql={call.sql} />
              <ResultTable call={call} />
            </section>
          ))}

          <section className="rounded-lg border border-dashed border-zinc-800 p-4 text-center text-xs text-zinc-600">
            chart visualization — planned (Recharts, observability sprint)
          </section>

          <Trace steps={result.run.steps} />
        </div>
      )}
    </main>
  );
}
