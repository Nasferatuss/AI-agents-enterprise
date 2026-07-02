# Screenshots

Drop demo captures here, then uncomment the matching `<!-- ![...] -->` block in the
top-level `README.md` (the "## Demo" section). Suggested set — the flagships first,
since they carry the "wow" in a 5-minute review:

| File | What to capture |
|---|---|
| `autonomous.gif` | `/autonomous` mid-run: the plan→act→reflect loop iterating, a tool call + result, a file written to the sandbox |
| `browse.gif` | `/browse` driving a real site (observe → act), ideally with the safety boundary refusing a destructive action |
| `research.png` | `/research` final report citing real source URLs, with the tool-call audit trail visible |
| `text2sql.png` | `/text2sql` answer + generated SQL + result table + reasoning trace (model, latency, cost) |
| `observability.png` | `/observability` dashboard: total runs, success rate, p95 latency, cost, failure taxonomy |
| `workflows.png` | `/workflows` paused at the approval gate with the risk assessment shown |

Tips: 1280–1440px wide, dark theme (the console default). For GIFs keep them short
(≤10s) and under a few MB so the README stays light. Record with the stack running
(`make up && make ui`) against a real provider so the numbers are non-zero.
