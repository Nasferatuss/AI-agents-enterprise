# ecc-hooks — hooks-only slice of everything-claude-code

Slim-плагин: подключает **только хуки** из вендорного `../everything-claude-code`,
не загружая его 156 skills / 38 agents / 72 commands (кураторский subset под наш стек
лежит в `.claude/` проекта и грузится оттуда).

## Как устроено

- `scripts/` — symlink на `../everything-claude-code/scripts`. Claude Code подставляет
  `${CLAUDE_PLUGIN_ROOT}` = корень этого плагина; скрипты резолвятся через symlink,
  их внутренние `require('../lib/...')` и `node_modules` — из вендорного репо
  (поэтому там нужен `npm install`).
- `hooks/hooks.json` — кураторская копия вендорного `hooks/hooks.json`. Что исключено
  и почему — в `_comment` внутри файла. Главное:
  - **lifecycle-хуки** (`session:start`, `pre:compact`, `stop:session-end`,
    `session:end:marker`, continuous-learning) исключены — их роль выполняет
    `claude-memory-compiler` (хуки в `.claude/settings.json`); наслаивать нельзя.
  - **JS/TS-хуки** (format-typecheck, console.log-чекеры, design-check) исключены —
    проект это markdown-вики + python.
  - `pre:write:doc-file-warning` исключён — ругался бы на каждый `wiki/*.md`.

## Подключение

В `.claude/settings.local.json`:

```json
{
  "extraKnownMarketplaces": {
    "ecc-hooks-local": {
      "source": { "source": "local", "path": ".../tools/ecc-hooks-plugin" }
    }
  },
  "enabledPlugins": { "ecc-hooks@ecc-hooks-local": true }
}
```

Хуки активируются с нового session (перезапустить Claude Code).

## Runtime-тюнинг (env)

- `ECC_HOOK_PROFILE=minimal|standard|strict` (default `standard`)
- `ECC_DISABLED_HOOKS=id1,id2` — точечно выключить хуки по id
