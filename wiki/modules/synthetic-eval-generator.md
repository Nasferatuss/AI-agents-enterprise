---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Synthetic Eval Generator

**Роль:** модуль №9 (post-MVP). Питает [[evals]] и [[rag-evaluation-lab]].

**Что делает:** из корпуса документов генерирует eval dataset — вопросы, эталонные
ответы, negative cases, multi-hop cases.

**Sprint 9 (1 нед):** Synthetic Eval Generator.
**DoD:** из корпуса документов создаётся eval dataset.
**Стек:** LLM API/local LLM, Pydantic.

**Риск:** датасет может быть недостоверным → human calibration subset, negative cases,
benchmark cards. См. [[risk-register]].

**Связи:** [[rag-evaluation-lab]], [[text-to-sql-rag-agent]], [[evals]].

## Sources
- `Дорожная карта.pdf` стр. 14 (Sprint 9).
