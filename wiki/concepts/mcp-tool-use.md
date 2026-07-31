---
type: concept
sources: ["project roadmap (internal)", "Anthropic — Model Context Protocol", "Anthropic — Building effective agents", "OpenAI — A practical guide to building agents"]
updated: 2026-06-13
---

# MCP / Tool Use

Платформенный **MCP / Tool Gateway**: servers, clients, tool registry, permissions.
Подключение SQL, browser, файлов, внешних API.

> Anthropic описывает MCP как открытый стандарт подключения AI-приложений к внешним
> системам и данным. Но это увеличивает security surface → проектировать с boundary:
> allowlist, permissions, audit log, no arbitrary shell → [[adr-005-mcp-security-boundary]].

## Что такое MCP (первоисточник Anthropic)

MCP — **open standard для secure, two-way connections** между источниками данных и
AI-инструментами. Решает проблему фрагментации: без стандарта каждый новый источник
данных требует собственной кастомной интеграции (M×N коннекторов), что не масштабируется.
MCP заменяет это единым протоколом — разработчик пишет интеграцию **против одного
стандарта**, а не против каждого источника по отдельности.

**Client/server-архитектура:**
- **MCP servers** — экспонируют данные и tools (источник → стандартизованный интерфейс).
- **MCP clients** (host-приложения, напр. сам AI-агент) — подключаются к серверам, чтобы
  retrieve информацию и вызывать tools.
- Замысел: AI-системы **сохраняют контекст**, перемещаясь между разными tools и датасетами.

При запуске Anthropic выпустила: спецификацию + SDK на GitHub; поддержку локальных MCP
servers в Claude Desktop; open-source репозиторий готовых серверов (Google Drive, Slack,
GitHub, Git, Postgres, Puppeteer). Ранние adopters: **Block, Apollo**; dev-tool компании
**Zed, Replit, Codeium, Sourcegraph**. Наш Tool Gateway реализует тот же client/server-контракт
поверх собственного permission-слоя.

## Типы tools (OpenAI — practical guide)

OpenAI выделяет **три типа tools** для агента:
- **Data** — retrieve контекст и информацию для исполнения workflow (query БД/CRM, чтение PDF,
  web search). Ср. [[rag]].
- **Action** — взаимодействие с системами для действий (запись в БД, апдейт записей, отправка
  сообщений, hand-off человеку). Именно к ним применяются tool safeguards → [[governance]].
- **Orchestration** — сам агент как tool для другого агента (Manager-паттерн, см. ниже).

Каждый tool — стандартизованное определение (many-to-many между tools и агентами);
well-documented, протестированные, переиспользуемые tools улучшают discoverability и
version management. При росте числа tools — разбивать задачи по нескольким агентам;
проблема не в количестве, а в их **похожести/overlap** (15+ чётких tools работают лучше,
чем <10 пересекающихся).

## Workflows vs Agents и паттерны оркестрации (Anthropic — building effective agents)

Базовое разграничение Anthropic:
- **Workflows** — системы, где LLM и tools оркестрируются через **предопределённые code paths**.
- **Agents** — системы, где LLM **динамически направляет собственные процессы и tool usage**.

Building block для обоих — **augmented LLM**: модель + retrieval + tools + memory (сама
генерирует search-запросы, выбирает tools, удерживает информацию). Ср. [[context-engineering]].

Пять named workflow-паттернов (от простого к сложному):
1. **Prompt chaining** — задача декомпозируется в последовательность шагов; каждый LLM-вызов
   обрабатывает выход предыдущего. Ложится на наш [[enterprise-workflow-orchestrator]].
2. **Routing** — классификация входа и направление в специализированную followup-задачу.
3. **Parallelization** — параллельная обработка независимых подзадач (sectioning) либо
   многократный прогон одной задачи с агрегацией (voting).
4. **Orchestrator-workers** — центральный LLM динамически дробит задачу, делегирует
   worker-LLM'ам и синтезирует результаты. (≈ Manager-паттерн OpenAI ниже.)
5. **Evaluator-optimizer** — один LLM генерирует ответ, другой даёт оценку и feedback в цикле.
   Ср. LLM-judges в [[evals]].

**Автономный агент** — LLM сам планирует и исполняет задачи через tools на основе feedback
из среды, в цикле с возможными human checkpoints.

Главный совет Anthropic: **«keep it simple»** — начинать с простого, добавлять сложность только
когда выигрыш доказуем; frameworks использовать осторожно (скрывают underlying mechanics);
заранее мерить cost/latency-tradeoffs. Это совпадает с [[adr-007-predictable-orchestration]].

## Single-agent vs multi-agent (OpenAI — practical guide)

OpenAI делит оркестрацию на две категории и рекомендует **сначала максимизировать
возможности single-agent** (инкрементально добавляя tools), переходя к multi-agent только
когда агент перестаёт следовать сложным инструкциям или путается в выборе tools:
- **Single-agent systems** — одна модель с tools и instructions исполняет workflow в loop
  (run = цикл до exit-условия: tool call, structured output, error, max turns).
- **Manager (agents as tools)** — центральный «manager»-агент координирует специализированных
  агентов через **tool calls** и синтезирует результаты (один агент держит контроль и доступ
  к пользователю). Это orchestration-тип tool выше.
- **Decentralized (handoffs)** — агенты-пиры **передают** (hand off) друг другу исполнение
  workflow; handoff — one-way transfer контроля + состояния разговора. Хорош для triage.

> Разница с Anthropic: OpenAI Manager-паттерн ≈ Anthropic orchestrator-workers, но OpenAI
> отдельно выделяет decentralized handoffs как самостоятельную категорию.

**Стек:** MCP SDK / JSON-RPC style contracts → [[tech-stack]].

**Модуль-витрина:** [[mcp-deep-research-agent]] (Sprint 7). Tool call success rate
80%+/90% → [[governance]].

## Sources
- `project roadmap (internal)` p. 3, 13.
- Anthropic — *Model Context Protocol*, https://www.anthropic.com/news/model-context-protocol
  — определение open standard, проблема M×N-фрагментации, client/server-модель, что выпущено
  (spec+SDK, Claude Desktop local servers, open-source серверы), early adopters (Block, Apollo,
  Zed, Replit, Codeium, Sourcegraph).
- Anthropic — *Building effective agents*, https://www.anthropic.com/research/building-effective-agents
  — определения workflows vs agents, augmented LLM, пять паттернов (prompt chaining, routing,
  parallelization, orchestrator-workers, evaluator-optimizer), «keep it simple».
- OpenAI — *A practical guide to building agents*,
  https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
  (PDF: cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)
  — три типа tools (data/action/orchestration), single-agent vs multi-agent, Manager- и
  Decentralized-паттерны, run-loop и exit-условия.
