---
type: concept
sources: ["Дорожная карта.pdf", "OpenAI — Computer use"]
updated: 2026-06-13
---

# Computer Use

Работа агента через UI (а не только API): смотрит экран → планирует действия → выполняет.

> OpenAI описывает computer-use как возможность модели работать с пользовательским
> интерфейсом; Anthropic называет computer use следующим frontier-направлением.

## Цикл computer-use (OpenAI — первоисточник, 5 шагов)

1. **Send initial request** — задача plain language + указание использовать computer tool для
   UI-взаимодействия.
2. **Screenshot-first turns** — модель может запросить screenshot перед действиями; ответ
   содержит `computer_call` с массивом `actions[]` (внутри — запрос `screenshot`).
3. **Execute all returned actions** — выполнить **по порядку** до следующего screenshot; actions
   батчатся в одном `computer_call`, harness исполняет их последовательно.
4. **Capture updated screenshot** — после действий снять полный UI, закодировать base64 и вернуть
   как `computer_call_output` (`detail: "original"` — макс. разрешение и точность клика).
5. **Repeat until tool stops** — на каждом follow-up слать `previous_response_id`, переиспользуя
   то же определение tool. Когда в ответе нет `computer_call` — оставшиеся output items =
   финальный ответ модели.

Этот while-loop (observe → act → screenshot) — то же ядро agent-loop, что run в [[mcp-tool-use]];
у нас action space реализован как observe/click/type через Tool Gateway.

**Action types (9):** `click`, `double_click`, `scroll`, `type`, `wait`, `keypress`, `drag`,
`move`, `screenshot`. Mouse-actions поддерживают опц. массив `keys` для модификаторов
(Ctrl+click, Shift+drag).

## Safety (OpenAI)

- **Environmental isolation** — браузер в изолированной среде, отключённые расширения и доступ к
  ФС; Docker с ограниченными permissions или headless Playwright.
- **Input validation** — screenshots, текст страницы, tool outputs, PDF, письма, чаты и любой
  third-party-контент трактовать как **untrusted input**; разрешением считаются только прямые
  инструкции пользователя. (Это та же prompt-injection-линия, что safety classifier в [[governance]].)
- **Human oversight** — human-in-the-loop на high-impact действиях; кастомные tools/harness для
  domain-специфичных guardrails и confirmation-флоу → [[adr-007-predictable-orchestration]].

> ⚠️ Противоречие: в дорожной карте/ранней заметке computer-use safety описывался через явные
> поля `pending_safety_checks` / `acknowledged_safety_checks` в ответе. В фактически прочитанной
> версии OpenAI-доки (*Computer use*, 2026-06-13) эти именованные поля **не показаны** — safety
> описан как environmental isolation + untrusted-input validation + human oversight. Возможны
> две версии API/документации; до перепроверки опираться на прочитанный first-source.
> Источники: `Дорожная карта.pdf`; OpenAI — *Computer use* (URL ниже).

**Ограничения (первоисточник):** работа в рамках разрешения screenshot и точности coordinate
mapping при downscaling изображений.

**Стек:** Playwright + screenshot/action traces; опц. computer-use API → [[tech-stack]].

**Модуль-витрина:** [[guarded-computer-use-qa-agent]] (Sprint 8) — на controlled legacy
UI sandbox с guardrails и retries.

**Метрики:** scenario completion, action accuracy, recovery after UI error, bug report
usefulness.

## Sources
- `Дорожная карта.pdf` стр. 4, 13–14.
- OpenAI — *Computer use*, https://developers.openai.com/api/docs/guides/tools-computer-use —
  5-шаговый цикл (`computer_call` / `computer_call_output`, `previous_response_id`), 9 action types,
  safety (environmental isolation, untrusted-input validation, human oversight), ограничения
  (resolution / coordinate mapping). Прим.: поля `pending_safety_checks`/`acknowledged_safety_checks`
  в прочитанной версии доки не показаны — см. блок Противоречие.
