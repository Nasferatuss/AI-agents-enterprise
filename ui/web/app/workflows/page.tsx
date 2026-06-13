"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type StepAttempt = {
  step: string;
  attempt: number;
  status: "succeeded" | "failed" | "retried";
  latency_ms: number;
  error?: string | null;
};

type ApprovalRecord = {
  step: string;
  decision: "approved" | "rejected";
  actor: string;
  reason?: string | null;
  decided_at: string;
};

type WorkflowRun = {
  id: string;
  workflow: string;
  status: "running" | "completed" | "failed" | "awaiting_approval" | "rejected";
  state: Record<string, unknown>;
  attempts: StepAttempt[];
  approvals: ApprovalRecord[];
  pending_step?: string | null;
  approval_prompt?: string | null;
  error?: string | null;
};

const STATUS_COLOR: Record<string, string> = {
  completed: "bg-emerald-500/15 text-emerald-400",
  rejected: "bg-red-500/15 text-red-400",
  failed: "bg-red-500/15 text-red-400",
  awaiting_approval: "bg-amber-500/15 text-amber-400",
  running: "bg-zinc-500/15 text-zinc-400",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded px-2 py-0.5 font-mono text-xs ${STATUS_COLOR[status] ?? "bg-zinc-500/15 text-zinc-400"}`}
    >
      {status}
    </span>
  );
}

export default function WorkflowsPage() {
  const [resource, setResource] = useState("production database");
  const [requester, setRequester] = useState("contractor@vendor.com");
  const [actor, setActor] = useState("security-officer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<WorkflowRun | null>(null);

  async function call(path: string, body: object) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const b = await res.json().catch(() => null);
        throw new Error(b?.detail ?? `HTTP ${res.status}`);
      }
      setRun((await res.json()) as WorkflowRun);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const start = () =>
    call("/v1/workflows/access_request/run", { input: { resource, requester } });
  const decide = (decision: "approve" | "reject") =>
    run && call(`/v1/workflows/runs/${run.id}/${decision}`, { actor });

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <p className="text-xs text-zinc-500">
        <a href="/" className="hover:text-zinc-300">
          ← workbench
        </a>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        Workflow Orchestrator
      </h1>
      <p className="mt-1 text-sm text-zinc-400">
        Predictable state machine with a human-in-the-loop approval gate before
        the risky action (ADR-007).
      </p>

      <section className="mt-8 grid gap-3 rounded-lg border border-zinc-800 p-5">
        <h2 className="text-sm font-medium text-zinc-300">
          Access request <span className="text-zinc-600">· access_request</span>
        </h2>
        <label className="text-xs text-zinc-400">
          Resource
          <input
            value={resource}
            onChange={(e) => setResource(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Requester
          <input
            value={requester}
            onChange={(e) => setRequester(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
          />
        </label>
        <button
          onClick={start}
          disabled={loading}
          className="mt-1 w-fit rounded-lg bg-zinc-100 px-5 py-2 text-sm font-medium text-zinc-900 disabled:opacity-40"
        >
          {loading ? "Running…" : "Start workflow"}
        </button>
      </section>

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      {run && (
        <div className="mt-8 space-y-5">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-medium text-zinc-300">
              Run <span className="font-mono text-zinc-500">{run.id}</span>
            </h2>
            <StatusBadge status={run.status} />
          </div>

          {run.status === "awaiting_approval" && (
            <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-5">
              <h3 className="text-sm font-medium text-amber-300">
                ⏸ Approval required — step “{run.pending_step}”
              </h3>
              <p className="mt-2 text-sm text-zinc-300">{run.approval_prompt}</p>
              {typeof run.state.risk_assessment === "string" && (
                <p className="mt-3 rounded bg-zinc-900/70 p-3 text-xs text-zinc-300">
                  <span className="text-zinc-500">risk assessment: </span>
                  {run.state.risk_assessment as string}
                </p>
              )}
              <div className="mt-4 flex items-center gap-2">
                <input
                  value={actor}
                  onChange={(e) => setActor(e.target.value)}
                  placeholder="your name (audit)"
                  className="flex-1 rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                />
                <button
                  onClick={() => decide("approve")}
                  disabled={loading || !actor.trim()}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  Approve
                </button>
                <button
                  onClick={() => decide("reject")}
                  disabled={loading || !actor.trim()}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  Reject
                </button>
              </div>
            </section>
          )}

          {run.status === "completed" && typeof run.state.grant_note === "string" && (
            <section className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm text-emerald-300">
              ✓ {run.state.grant_note as string}
            </section>
          )}
          {run.status === "rejected" && (
            <section className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-300">
              ✕ {run.error}
            </section>
          )}

          {run.approvals.length > 0 && (
            <section className="rounded-lg border border-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-300">Audit log</h3>
              <ul className="mt-2 space-y-1">
                {run.approvals.map((a, i) => (
                  <li key={i} className="font-mono text-xs text-zinc-400">
                    <span
                      className={
                        a.decision === "approved"
                          ? "text-emerald-400"
                          : "text-red-400"
                      }
                    >
                      {a.decision}
                    </span>{" "}
                    · {a.step} · by {a.actor} · {a.decided_at}
                    {a.reason ? ` · “${a.reason}”` : ""}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <details className="rounded-lg border border-zinc-800 p-4">
            <summary className="cursor-pointer text-sm font-medium text-zinc-300">
              Step trace · {run.attempts.length} attempt
              {run.attempts.length === 1 ? "" : "s"}
            </summary>
            <ol className="mt-3 space-y-1">
              {run.attempts.map((a, i) => (
                <li key={i} className="font-mono text-xs text-zinc-400">
                  {a.step} #{a.attempt}{" "}
                  <span
                    className={
                      a.status === "succeeded"
                        ? "text-emerald-400"
                        : a.status === "retried"
                          ? "text-amber-400"
                          : "text-red-400"
                    }
                  >
                    {a.status}
                  </span>{" "}
                  · {a.latency_ms}ms
                  {a.error ? ` · ${a.error}` : ""}
                </li>
              ))}
            </ol>
          </details>
        </div>
      )}
    </main>
  );
}
