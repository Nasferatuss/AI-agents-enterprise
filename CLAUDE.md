# Enterprise AI Agent Workbench — knowledge base conventions

This file is the schema for `wiki/`: how pages are structured, named, linked and
kept honest. It is read by Claude Code when working in this repository; it is not
a description of the platform itself — that is [README.md](README.md).

The pattern: an LLM incrementally builds and maintains a linked markdown wiki on
top of immutable primary sources. The human owns the sources, the research and the
questions; the LLM does the routine — summarizing, cross-referencing, filing,
bookkeeping.

## Two layers

1. **`wiki/`** — markdown pages the LLM fully owns: creates, updates, links and
   keeps consistent.
2. **`CLAUDE.md`** (this file) — the schema: wiki structure, conventions, workflow.
   It co-evolves as it becomes clear what works.

Primary sources (roadmap, papers, transcripts) are **not** part of this
repository. Pages still cite them by name and page number so that provenance is
auditable, but the documents themselves stay internal.

## Language

Wiki prose is in **Russian** — it is a working knowledge base, not a public
deliverable. Technical terms stay in English (RAG, eval, trace, orchestrator,
guardrails, tool call, retrieval) and are never translated. Code, comments,
commit messages and everything under `docs/` are English.

Keep pages short and dense. Engineering tone, no filler.

## Structure of `wiki/`

```
wiki/
├── 00_index.md          # map of the wiki: table of contents, links, project status
├── architecture/        # Service-Oriented Core + one page per platform layer
├── modules/             # one page per demo module
├── concepts/            # cross-cutting: RAG, evals, MCP, observability, governance, context engineering
└── decisions/           # key decisions with rationale (ADR style)
```

## Page conventions

- **File names**: `kebab-case.md`, Latin script, named after the subject
  (`text-to-sql-rag-agent.md`, `service-oriented-core.md`).
- **Cross-links**: Obsidian style `[[file-name-without-extension]]`. Link
  generously — a link to a page that does not exist yet is fine, it marks a page
  worth writing.
- **Frontmatter** on every page:
  ```yaml
  ---
  type: module | architecture | concept | decision | index
  status: draft | active | done | deprecated
  sources: ["project roadmap (internal)"]
  updated: 2026-06-07
  ---
  ```
- **Sources section** at the bottom: where the information came from, and where
  exactly — page of the PDF, section of the article. This is what makes a claim
  checkable instead of merely asserted.
- **Contradictions**: when a new source contradicts what is already in the wiki,
  do **not** overwrite silently. Add a `> ⚠️ Противоречие:` block with both
  versions and their sources. A synthesis is a visible compromise, not a
  rewritten history.

## Workflow

### Ingesting a source
1. Read it end to end. For PDFs use `pypdf` (below) rather than the built-in
   renderer.
2. Extract the entities, facts, decisions, risks and metrics.
3. **Integrate, do not duplicate**: update existing pages where the source
   extends them; create a new page only for a genuinely new entity.
4. Update cross-links and `00_index.md`. Bump `updated:` and extend `sources:`.
5. Flag contradictions with the existing content.

### Answering a question
1. Look in `wiki/` first — it is already synthesised. If the answer is there,
   answer from it and link.
2. A gap in the wiki is a signal: answer from the sources *and* fill the page in.

### Maintenance
- After any large change, check `00_index.md` and look for broken or missing links.
- Keep module `status:` current as work progresses.

## Extracting text from a PDF

The built-in PDF renderer needs poppler and may be unavailable. The reliable path
is `pypdf`:

```bash
python3 - <<'EOF'
from pypdf import PdfReader
r = PdfReader("path/to/source.pdf")
for i, p in enumerate(r.pages):
    print(f"\n=== PAGE {i+1} ===\n{p.extract_text() or ''}")
EOF
```

## The principle

The wiki is a persistent, compounding artifact. Cross-references are already in
place, contradictions are already marked, the synthesis already reflects
everything that was read. Each source and each question makes it richer.
Knowledge is compiled once and kept current, rather than re-derived per request.
