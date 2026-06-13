const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type DependencyStatus = {
  name: string;
  state: "ok" | "unreachable" | "skipped";
  detail?: string | null;
};

type HealthReport = {
  service: string;
  version: string;
  env: string;
  status: "ok" | "degraded";
  dependencies: DependencyStatus[];
};

async function fetchHealth(): Promise<HealthReport | null> {
  try {
    const res = await fetch(`${API_URL}/healthz/deps`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as HealthReport;
  } catch {
    return null;
  }
}

function StateBadge({ state }: { state: string }) {
  const color =
    state === "ok"
      ? "bg-emerald-500/15 text-emerald-400"
      : "bg-red-500/15 text-red-400";
  return (
    <span className={`rounded px-2 py-0.5 font-mono text-xs ${color}`}>
      {state}
    </span>
  );
}

export default async function Home() {
  const health = await fetchHealth();

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        Enterprise AI Agent Workbench
      </h1>
      <p className="mt-2 text-sm text-zinc-400">
        Service-oriented platform for production-grade AI agents — demo console
        (Sprint 0 skeleton).
      </p>

      <section className="mt-10 rounded-lg border border-zinc-800 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-300">Platform status</h2>
          {health ? (
            <StateBadge state={health.status} />
          ) : (
            <StateBadge state="gateway unreachable" />
          )}
        </div>
        <ul className="mt-4 space-y-2">
          <li className="flex items-center justify-between text-sm">
            <span className="text-zinc-400">api gateway</span>
            <StateBadge state={health ? "ok" : "unreachable"} />
          </li>
          {health?.dependencies.map((dep) => (
            <li
              key={dep.name}
              className="flex items-center justify-between text-sm"
            >
              <span className="text-zinc-400">{dep.name}</span>
              <StateBadge state={dep.state} />
            </li>
          ))}
        </ul>
        {!health && (
          <p className="mt-4 text-xs text-zinc-500">
            Start the stack with <code className="font-mono">make up</code> (or{" "}
            <code className="font-mono">make api</code> for the gateway alone).
          </p>
        )}
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-medium text-zinc-300">Modules</h2>
        <div className="mt-3 grid gap-3">
          <a
            href="/text2sql"
            className="group rounded-lg border border-zinc-800 p-5 transition-colors hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-100">
                Text-to-SQL BI Agent
              </h3>
              <span className="text-zinc-600 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              Business question → SQL → result → explanation, with read-only
              guards (ADR-004).
            </p>
          </a>
          <a
            href="/workflows"
            className="group rounded-lg border border-zinc-800 p-5 transition-colors hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-100">
                Workflow Orchestrator
              </h3>
              <span className="text-zinc-600 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              Predictable workflows with a human-in-the-loop approval gate and
              audit log (ADR-007).
            </p>
          </a>
          <a
            href="/observability"
            className="group rounded-lg border border-zinc-800 p-5 transition-colors hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-100">
                Observability Console
              </h3>
              <span className="text-zinc-600 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              Traces for every run — cost, latency, and failure taxonomy across
              the platform (ADR-006).
            </p>
          </a>
          <a
            href="/process"
            className="group rounded-lg border border-zinc-800 p-5 transition-colors hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-100">
                Business Process Investigator
              </h3>
              <span className="text-zinc-600 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              A spec → entities, process map, contradictions, and a backlog.
            </p>
          </a>
          <a
            href="/compliance"
            className="group rounded-lg border border-zinc-800 p-5 transition-colors hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-100">
                Compliance & Risk Reviewer
              </h3>
              <span className="text-zinc-600 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              PII detection + policy rules + a deterministic risk score.
            </p>
          </a>
          <a
            href="/research"
            className="group rounded-lg border border-zinc-800 p-5 transition-colors hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-100">
                Deep Research Agent
              </h3>
              <span className="text-zinc-600 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              Plan → research via a governed Tool Gateway → cited report with an
              audit log (ADR-005).
            </p>
          </a>
          <a
            href="/qa"
            className="group rounded-lg border border-zinc-800 p-5 transition-colors hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-100">
                Guarded Computer-Use QA
              </h3>
              <span className="text-zinc-600 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              A QA agent drives a legacy UI sandbox through a guarded action space
              and reports bugs.
            </p>
          </a>
          <a
            href="/incidents"
            className="group rounded-lg border border-zinc-800 p-5 transition-colors hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-100">
                Incident Response
              </h3>
              <span className="text-zinc-600 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              Failed runs → deterministic root-cause classification → RCA report.
            </p>
          </a>
        </div>
      </section>
    </main>
  );
}
