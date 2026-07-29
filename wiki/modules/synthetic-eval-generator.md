---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# Synthetic Eval Generator

**Роль:** модуль №9 (post-MVP). Питает [[evals]] и [[rag-evaluation-lab]].

**Что делает:** из корпуса документов генерирует eval dataset — вопросы, эталонные
ответы, negative cases, multi-hop cases.

**Sprint 9 (1 нед):** Synthetic Eval Generator. ✅ done 2026-06-13: `platform/evals/generator.py`
(`generate_eval_dataset`) расширяет базовую генерацию тремя типами кейсов: **standard**
(answerable + reference answer), **negative** (off-corpus → система обязана отказать; relevant_sources
пустые → метрика refusal accuracy), **multihop** (нужны два источника). Плюс **benchmark card** —
калибровочный артефакт (состав по типам, source coverage, generating model + note про human-
calibration) — прямо митигирует риск «датасет недостоверен». API `POST /v1/evals/generate`.
Скармливается в eval runner → замыкает цикл с [[rag-evaluation-lab]].
**DoD выполнен.**
**Стек:** LLM API/local LLM, Pydantic.

**Риск:** датасет может быть недостоверным → human calibration subset, negative cases,
benchmark cards.

**Связи:** [[rag-evaluation-lab]], [[text-to-sql-rag-agent]], [[evals]].

## Sources
- `Дорожная карта.pdf` стр. 14 (Sprint 9).
