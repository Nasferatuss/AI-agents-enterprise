---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# Business Process Investigator

**Роль:** модуль №5 (post-MVP).

**Что делает:** документ → сущности → процесс → противоречия → backlog.
На sample ТЗ формирует process map (Mermaid) и список задач.

**Sprint 6 (1 нед):** Process Investigator. ✅ done 2026-06-13: `apps/process_investigator`
(`workbench-app-process`) — один structured LLM-вызов (complexity=complex) извлекает
entities / ordered steps / contradictions / backlog из документа; **process map (Mermaid)
рендерится чистым кодом** из шагов (детерминированно, `to_mermaid`). API
`POST /v1/apps/process/analyze`, страница `/process` в UI (entities, mermaid-source,
contradictions, backlog), sample ТЗ в `examples/docs/sample_spec.md`. **DoD выполнен**:
на sample ТЗ формируется process map + backlog.
**Стек:** RAG Core, LLM, Mermaid.

**Связи:** [[rag]], [[compliance-risk-reviewer]] (идёт в той же паре спринтов).

## Sources
- `Дорожная карта.pdf` стр. 12–13 (Sprint 6).
