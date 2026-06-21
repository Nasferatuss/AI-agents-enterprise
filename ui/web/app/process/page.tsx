"use client";

import { useEffect, useState } from "react";
import DOMPurify from "isomorphic-dompurify";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let mermaidReady = false;

function MermaidDiagram({ code }: { code: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailed(false);

    // Dynamic import keeps mermaid client-only so `next build` (SSR) never
    // touches `window` at module load.
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        if (!mermaidReady) {
          mermaid.initialize({ startOnLoad: false, theme: "dark" });
          mermaidReady = true;
        }
        const id = `mermaid-${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(id, code);
        // mermaid output is derived from LLM-generated text; sanitize before
        // injecting via dangerouslySetInnerHTML to neutralize any XSS vector.
        const clean = DOMPurify.sanitize(svg, {
          USE_PROFILES: { svg: true, svgFilters: true },
        });
        if (!cancelled) setSvg(clean);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code]);

  if (failed) {
    return (
      <pre className="mt-2 overflow-x-auto rounded-lg bg-zinc-950 p-3 text-xs leading-relaxed text-sky-300">
        {code}
      </pre>
    );
  }

  if (!svg) {
    return (
      <p className="mt-2 rounded-lg bg-zinc-950 p-3 text-xs text-zinc-500">
        rendering diagram…
      </p>
    );
  }

  return (
    <div className="mt-2 space-y-2">
      <div
        className="overflow-x-auto rounded-lg bg-zinc-950 p-3 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <details className="text-[11px] text-zinc-600">
        <summary className="cursor-pointer hover:text-zinc-400">
          show source
        </summary>
        <pre className="mt-1 overflow-x-auto rounded-lg bg-zinc-950 p-3 leading-relaxed text-sky-300">
          {code}
        </pre>
      </details>
    </div>
  );
}

const SAMPLE = `When a new employee joins, HR creates a record in the HR system. IT provisions a laptop and creates accounts in the identity provider. The employee receives a welcome email with shared credentials for the team wiki. The manager approves access to the production database. However, an earlier section states contractors may never access production — it is unclear who approves access for a contractor. There is no statement about data retention for terminated employees.`;

type Entity = { name: string; type: string };
type Step = { id: number; actor: string; action: string; next: number[] };
type Backlog = { title: string; priority: "high" | "medium" | "low" };
type Report = {
  entities: Entity[];
  steps: Step[];
  contradictions: string[];
  backlog: Backlog[];
  mermaid: string;
  provider: string;
  model: string;
};

const PRIO_COLOR: Record<string, string> = {
  high: "text-red-400",
  medium: "text-amber-400",
  low: "text-zinc-400",
};

export default function ProcessPage() {
  const [doc, setDoc] = useState(SAMPLE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);

  async function analyze() {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await fetch(`${API_URL}/v1/apps/process/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document: doc }),
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
        Business Process Investigator
      </h1>
      <p className="mt-1 text-sm text-zinc-400">
        A spec becomes entities, a process map, contradictions, and a backlog.
      </p>

      <textarea
        value={doc}
        onChange={(e) => setDoc(e.target.value)}
        rows={6}
        className="mt-6 w-full rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
      />
      <button
        onClick={analyze}
        disabled={loading || !doc.trim()}
        className="mt-3 rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
      >
        {loading ? "Analyzing…" : "Investigate"}
      </button>

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      {report && (
        <div className="mt-8 space-y-5">
          <section>
            <h2 className="text-sm font-medium text-zinc-300">Entities</h2>
            <div className="mt-2 flex flex-wrap gap-2">
              {report.entities.map((e, i) => (
                <span
                  key={i}
                  className="rounded-full border border-zinc-800 px-3 py-1 text-xs text-zinc-300"
                >
                  {e.name}{" "}
                  <span className="text-zinc-600">· {e.type}</span>
                </span>
              ))}
            </div>
          </section>

          <section>
            <h2 className="text-sm font-medium text-zinc-300">
              Process map <span className="text-zinc-600">(Mermaid)</span>
            </h2>
            <MermaidDiagram code={report.mermaid} />
          </section>

          {report.contradictions.length > 0 && (
            <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
              <h2 className="text-sm font-medium text-amber-300">
                Contradictions & gaps
              </h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-300">
                {report.contradictions.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h2 className="text-sm font-medium text-zinc-300">Backlog</h2>
            <ul className="mt-2 space-y-1">
              {report.backlog.map((b, i) => (
                <li key={i} className="flex items-center gap-2 text-sm text-zinc-200">
                  <span className={`font-mono text-xs ${PRIO_COLOR[b.priority]}`}>
                    [{b.priority}]
                  </span>
                  {b.title}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </main>
  );
}
