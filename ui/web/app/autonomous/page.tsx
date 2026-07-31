"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Plan = { steps: string[] };

type Reflection = {
  goal_met: boolean;
  missing: string;
  next_focus: string;
};

// `actions` is the acting agent's final answer for the round. The backend
// currently serializes it as a string, but we stay defensive: it may also
// arrive as an AgentRun-ish object with `final_text` / `steps`.
type Actions =
  | string
  | {
      final_text?: string | null;
      steps?: unknown[];
      [k: string]: unknown;
    };

type Iteration = {
  plan: Plan;
  actions: Actions;
  reflection: Reflection;
};

type AutonomousResult = {
  goal: string;
  iterations: Iteration[];
  memory: string[];
  final_answer: string;
  completed: boolean;
  cost_usd: number | null;
};

const PLACEHOLDER = "Compute 17*23 and explain the result";

const EXAMPLES = [
  "Compute 17*23 and explain the result",
  "How many seconds are left until the end of the current hour?",
  "Evaluate 2**10 and compare it to 1000",
];

// Pull a human-readable final answer + step count out of `actions`, whether it
// is a plain string or an AgentRun-ish object.
function readActions(actions: Actions): { text: string; stepCount: number | null } {
  if (typeof actions === "string") {
    return { text: actions, stepCount: null };
  }
  if (actions && typeof actions === "object") {
    const text = typeof actions.final_text === "string" ? actions.final_text : "";
    const stepCount = Array.isArray(actions.steps) ? actions.steps.length : null;
    return { text, stepCount };
  }
  return { text: "", stepCount: null };
}

function IterationCard({ it, index }: { it: Iteration; index: number }) {
  const { text, stepCount } = readActions(it.actions);
  const met = it.reflection.goal_met;

  return (
    <section className="rounded-lg border border-zinc-800 p-4">
      <h3 className="text-sm font-semibold text-zinc-200">
        Iteration {index + 1}
      </h3>

      <div className="mt-3">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          Plan
        </p>
        {it.plan.steps.length > 0 ? (
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-zinc-300">
            {it.plan.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        ) : (
          <p className="mt-1 text-sm text-zinc-600">(no steps)</p>
        )}
      </div>

      <div className="mt-3">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          Act
          {stepCount != null && (
            <span className="ml-2 font-normal normal-case text-zinc-600">
              {stepCount} tool step{stepCount === 1 ? "" : "s"}
            </span>
          )}
        </p>
        <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-300">
          {text || "(no result)"}
        </p>
      </div>

      <div className="mt-3">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          Reflection
        </p>
        <p className="mt-1 text-sm">
          <span className={met ? "text-emerald-400" : "text-amber-400"}>
            {met ? "✓ goal met" : "✗ not yet"}
          </span>
        </p>
        {!met && it.reflection.missing && (
          <p className="mt-1 text-sm text-zinc-400">
            <span className="text-zinc-500">missing:</span>{" "}
            {it.reflection.missing}
          </p>
        )}
        {!met && it.reflection.next_focus && (
          <p className="mt-1 text-sm text-zinc-400">
            <span className="text-zinc-500">next focus:</span>{" "}
            {it.reflection.next_focus}
          </p>
        )}
      </div>
    </section>
  );
}

export default function AutonomousPage() {
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AutonomousResult | null>(null);

  async function run(g: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/v1/apps/autonomous/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: g }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        if (res.status === 503) {
          throw new Error(
            body?.detail ??
              "No LLM provider configured (503). Set an API key for a model provider on the gateway.",
          );
        }
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setResult((await res.json()) as AutonomousResult);
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
        Autonomous Agent
      </h1>
      <p className="mt-1 text-sm text-zinc-400">
        Autonomous agent — plans, acts with tools, reflects, and repeats until
        the goal is met.
      </p>

      <form
        className="mt-8"
        onSubmit={(e) => {
          e.preventDefault();
          if (goal.trim()) run(goal.trim());
        }}
      >
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          rows={3}
          placeholder={PLACEHOLDER}
          className="w-full rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
        />
        <button
          type="submit"
          disabled={loading || !goal.trim()}
          className="mt-3 rounded-lg bg-violet-600 px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "Running…" : "Run"}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setGoal(ex);
              run(ex);
            }}
            disabled={loading}
            className="rounded-full border border-zinc-800 px-3 py-1 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 disabled:opacity-40"
          >
            {ex}
          </button>
        ))}
      </div>

      {loading && (
        <p className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 text-sm text-zinc-400">
          Running the plan → act → reflect loop… autonomous runs can take
          10–60s.
        </p>
      )}

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-8 space-y-5">
          <section className="flex flex-wrap items-center gap-3 text-sm">
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                result.completed
                  ? "bg-emerald-500/10 text-emerald-400"
                  : "bg-amber-500/10 text-amber-400"
              }`}
            >
              {result.completed ? "✓ completed" : "max steps reached"}
            </span>
            <span className="text-zinc-400">
              {result.iterations.length} iteration
              {result.iterations.length === 1 ? "" : "s"}
            </span>
            {result.cost_usd != null && (
              <span className="text-zinc-500">
                ${result.cost_usd.toFixed(5)}
              </span>
            )}
          </section>

          <div className="space-y-4">
            {result.iterations.map((it, i) => (
              <IterationCard key={i} it={it} index={i} />
            ))}
          </div>

          {result.memory.length > 0 && (
            <section className="rounded-lg border border-zinc-800 p-4">
              <h2 className="text-sm font-medium text-zinc-300">
                Memory{" "}
                <span className="text-zinc-600">(scratchpad)</span>
              </h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-400">
                {result.memory.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
            <h2 className="text-sm font-medium text-violet-300">
              Final answer
            </h2>
            <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-100">
              {result.final_answer || "(agent produced no final answer)"}
            </p>
          </section>
        </div>
      )}
    </main>
  );
}
