"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SAMPLE = `The onboarding record stores the employee's SSN 123-45-6789 and personal email jane.doe@example.com. The team uses shared credentials for the wiki. Encryption may be disabled for the staging environment to speed up testing. There is no statement about data retention for terminated employees.`;

type PiiFinding = { type: string; count: number; example: string };
type Violation = { rule_id: string; description: string; severity: string };
type Report = {
  risk_score: number;
  risk_band: "low" | "medium" | "high" | "critical";
  pii_findings: PiiFinding[];
  policy_violations: Violation[];
  summary: string;
  recommendations: string[];
};

const BAND_COLOR: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  medium: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
};
const SEV_COLOR: Record<string, string> = {
  high: "text-red-400",
  medium: "text-amber-400",
  low: "text-zinc-400",
};

export default function CompliancePage() {
  const [doc, setDoc] = useState(SAMPLE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);

  async function send(req: () => Promise<Response>) {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await req();
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

  function review() {
    return send(() =>
      fetch(`${API_URL}/v1/apps/compliance/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document: doc }),
      }),
    );
  }

  function reviewFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-uploading the same file
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    return send(() =>
      fetch(`${API_URL}/v1/apps/compliance/review/file`, {
        method: "POST",
        body: form,
      }),
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <p className="text-xs text-zinc-500">
        <a href="/" className="hover:text-zinc-300">
          ← workbench
        </a>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        Compliance & Risk Reviewer
      </h1>
      <p className="mt-1 text-sm text-zinc-400">
        Deterministic PII detection + policy rules + a reproducible risk score —
        the LLM only explains the findings, it never sets the number.
      </p>

      <textarea
        value={doc}
        onChange={(e) => setDoc(e.target.value)}
        rows={5}
        className="mt-6 w-full rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
      />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          onClick={review}
          disabled={loading || !doc.trim()}
          className="rounded-lg bg-violet-600 px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "Reviewing…" : "Review document"}
        </button>
        <span className="text-xs text-zinc-600">or</span>
        <label className="cursor-pointer rounded-lg border border-zinc-700 px-5 py-2 text-sm font-medium text-zinc-300 hover:border-zinc-500">
          Upload file
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={reviewFile}
            disabled={loading}
            className="hidden"
          />
        </label>
        <span className="text-xs text-zinc-600">PDF, DOCX, TXT, MD</span>
      </div>

      {error && (
        <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      {report && (
        <div className="mt-8 space-y-5">
          <section
            className={`flex items-center justify-between rounded-lg border p-5 ${BAND_COLOR[report.risk_band]}`}
          >
            <div>
              <p className="text-xs uppercase tracking-wide opacity-70">Risk</p>
              <p className="text-2xl font-semibold">{report.risk_band}</p>
            </div>
            <p className="font-mono text-3xl font-semibold">
              {report.risk_score}
              <span className="text-base opacity-50">/100</span>
            </p>
          </section>

          <section className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 p-4">
              <h2 className="text-sm font-medium text-zinc-300">PII detected</h2>
              {report.pii_findings.length === 0 ? (
                <p className="mt-2 text-xs text-zinc-500">none</p>
              ) : (
                <ul className="mt-2 space-y-1 text-sm">
                  {report.pii_findings.map((f, i) => (
                    <li key={i} className="text-zinc-300">
                      <span className="font-mono text-xs text-zinc-500">
                        {f.count}×
                      </span>{" "}
                      {f.type}{" "}
                      <span className="font-mono text-xs text-zinc-600">
                        {f.example}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-lg border border-zinc-800 p-4">
              <h2 className="text-sm font-medium text-zinc-300">
                Policy violations
              </h2>
              {report.policy_violations.length === 0 ? (
                <p className="mt-2 text-xs text-zinc-500">none</p>
              ) : (
                <ul className="mt-2 space-y-1.5 text-sm">
                  {report.policy_violations.map((v, i) => (
                    <li key={i} className="text-zinc-300">
                      <span className={`font-mono text-xs ${SEV_COLOR[v.severity]}`}>
                        [{v.severity}]
                      </span>{" "}
                      {v.description}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          {(report.summary || report.recommendations.length > 0) && (
            <section className="rounded-lg border border-zinc-800 p-4">
              <h2 className="text-sm font-medium text-zinc-300">
                Reviewer summary
              </h2>
              {report.summary && (
                <p className="mt-2 text-sm text-zinc-300">{report.summary}</p>
              )}
              {report.recommendations.length > 0 && (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-zinc-300">
                  {report.recommendations.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>
      )}
    </main>
  );
}
