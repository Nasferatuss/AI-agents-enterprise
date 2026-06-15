"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type BrowseStep = {
  observation_summary: string;
  action: Record<string, unknown>;
  note?: string | null;
};

type BrowseResult = {
  url: string;
  goal: string;
  steps: BrowseStep[];
  answer: string;
  completed: boolean;
  provider?: string | null;
  cost_usd?: number | null;
};

const MAX_OBS_CHARS = 160;

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + "…" : text;
}

function formatAction(action: Record<string, unknown>): string {
  const kind = action.action;
  if (typeof kind === "string") {
    const rest = Object.entries(action)
      .filter(([k]) => k !== "action")
      .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
      .join("  ");
    return rest ? `${kind} · ${rest}` : kind;
  }
  return JSON.stringify(action);
}

function StepRow({ step, index }: { step: BrowseStep; index: number }) {
  return (
    <li className="rounded bg-zinc-900/60 p-3 text-xs">
      <p className="mb-1 font-mono text-[11px] text-zinc-500">
        step {index + 1} · {step.observation_summary
          ? truncate(step.observation_summary, MAX_OBS_CHARS)
          : "(no observation)"}
      </p>
      <p className="font-mono text-[11px] text-sky-300">
        → {formatAction(step.action)}
      </p>
      {step.note && (
        <p className="mt-1 font-mono text-[11px] text-amber-400">⚠ {step.note}</p>
      )}
    </li>
  );
}

export default function BrowsePage() {
  const [url, setUrl] = useState("");
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chromiumMissing, setChromiumMissing] = useState(false);
  const [result, setResult] = useState<BrowseResult | null>(null);

  async function browse() {
    setLoading(true);
    setError(null);
    setChromiumMissing(false);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/v1/apps/cua/browse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), goal: goal.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail =
          typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
        if (res.status === 503 || /chromium|playwright|browser/i.test(detail)) {
          setChromiumMissing(true);
          return;
        }
        throw new Error(detail);
      }
      setResult((await res.json()) as BrowseResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const canSubmit =
    url.trim().length > 0 && goal.trim().length > 0 && !loading;

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <p className="text-xs text-zinc-500">
        <a href="/" className="hover:text-zinc-300">
          ← workbench
        </a>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        Computer-Use Live Browsing
      </h1>
      <p className="mt-1 text-sm text-zinc-400">
        Computer-use agent — opens a real website and drives it toward your goal
        (observe → act → repeat).
      </p>

      <form
        className="mt-8 space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) browse();
        }}
      >
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com"
          className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm outline-none placeholder:text-zinc-600 focus:border-zinc-600"
        />
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="What is the main heading on this page?"
          rows={2}
          className="w-full resize-y rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm outline-none placeholder:text-zinc-600 focus:border-zinc-600"
        />
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "Browsing…" : "Browse"}
        </button>
        {loading && (
          <p className="text-[11px] text-zinc-500">
            Driving a real headless browser — this can take 10–40s.
          </p>
        )}
      </form>

      {chromiumMissing && (
        <div className="mt-6 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-300">
          <p className="font-medium">Live browser unavailable</p>
          <p className="mt-1 text-amber-300/80">
            Chromium isn&apos;t installed in the API container, so the
            computer-use agent can&apos;t open a real browser here. This flagship
            runs locally — start the API on your machine and install the browser
            with{" "}
            <code className="rounded bg-zinc-900 px-1.5 py-0.5 font-mono text-xs text-amber-200">
              playwright install chromium
            </code>
            , then try again.
          </p>
        </div>
      )}

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-8 space-y-5">
          <section className="rounded-lg border border-zinc-800 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm text-zinc-200">{result.goal}</p>
                <a
                  href={result.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate font-mono text-[11px] text-sky-400 hover:text-sky-300"
                >
                  {result.url}
                </a>
              </div>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium ${
                  result.completed
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-amber-500/10 text-amber-400"
                }`}
              >
                {result.completed ? "completed" : "incomplete"}
              </span>
            </div>
            {(result.provider || result.cost_usd != null) && (
              <p className="mt-3 font-mono text-[11px] text-zinc-500">
                {result.provider ?? "—"}
                {result.cost_usd != null &&
                  ` · $${result.cost_usd.toFixed(5)}`}
              </p>
            )}
          </section>

          <section className="rounded-lg border border-zinc-800 p-4">
            <h2 className="text-sm font-medium text-zinc-300">Answer</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-100">
              {result.answer || "(no answer produced)"}
            </p>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-300">
              Trace · {result.steps.length} step
              {result.steps.length === 1 ? "" : "s"}
            </h2>
            <ol className="space-y-2">
              {result.steps.map((step, i) => (
                <StepRow key={i} step={step} index={i} />
              ))}
              {result.steps.length === 0 && (
                <li className="rounded bg-zinc-900/60 p-3 text-xs text-zinc-600">
                  No steps recorded.
                </li>
              )}
            </ol>
            <p className="mt-3 text-[11px] text-zinc-600">
              Safety boundary: the agent only clicks / types / navigates /
              finishes, and refuses payment, checkout, and destructive actions.
            </p>
          </section>
        </div>
      )}
    </main>
  );
}
