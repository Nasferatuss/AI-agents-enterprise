# Настройка окружения (ADR-009: сервис на Mac, GPU-машина = inference)

Пошаговая инструкция: что, где и как прописать. Делается один раз.

---

## Часть 1. GPU-машина (RTX 4090) — поднять Ollama для сети

### 1.1. Проверить, что Ollama установлена

Открой терминал (на Windows — PowerShell) и выполни:

```
ollama --version
```

Если команды нет — поставить с https://ollama.com/download.

### 1.2. Заставить Ollama слушать сеть, а не только localhost

По умолчанию Ollama принимает запросы только с самой машины. Нужна переменная
окружения `OLLAMA_HOST=0.0.0.0`.

**Windows:**
1. `Win + R` → `sysdm.cpl` → вкладка «Дополнительно» → «Переменные среды».
2. В «Переменные среды пользователя» → «Создать»:
   - Имя: `OLLAMA_HOST`
   - Значение: `0.0.0.0`
3. Полностью выйти из Ollama (иконка в трее → Quit) и запустить заново.

**Linux (systemd):**
```bash
sudo systemctl edit ollama
# в открывшемся файле добавить:
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0"
sudo systemctl restart ollama
```

### 1.3. Открыть порт 11434 в файрволе — только для локальной сети

**Windows (PowerShell от администратора):**
```powershell
New-NetFirewallRule -DisplayName "Ollama LAN" -Direction Inbound -Protocol TCP `
  -LocalPort 11434 -RemoteAddress LocalSubnet -Action Allow
```
`-RemoteAddress LocalSubnet` — ключевое: порт открыт только для домашней сети,
не для интернета (у Ollama нет авторизации).

**Linux (ufw):** `sudo ufw allow from 192.168.0.0/16 to any port 11434`

### 1.4. Скачать модели

```
ollama pull nomic-embed-text        # embeddings для RAG (~270MB)
ollama pull qwen2.5:3b-instruct     # simple-tier LLM
# позже, для бесплатного standard-tier (рекомендую):
ollama pull qwen3:14b
```

> Если Qwen-модели у тебя скачаны не через Ollama (сырые веса HuggingFace /
> LM Studio) — для Ollama их нужно скачать её командой `pull`, она хранит модели
> в своём формате. Либо вместо Ollama поднять LM Studio Server / vLLM — они тоже
> дают OpenAI-compatible API, тогда в Части 3 просто укажи их адрес и порт.

### 1.5. Узнать имя машины

```
hostname
```
Допустим, вывело `GAMING-PC`. Тогда адрес для Mac: `http://gaming-pc.local:11434`.

---

## Часть 2 (рекомендуется). Tailscale — стабильное имя без статического IP

`*.local` работает только в одной LAN и не резолвится внутри Docker-контейнеров.
Tailscale снимает обе проблемы: бесплатно, 10 минут.

1. https://tailscale.com/download → поставить **на обе машины** (Mac и GPU).
2. Залогиниться **одним и тем же** аккаунтом (Google/GitHub).
3. В админке https://login.tailscale.com/admin/dns включить **MagicDNS**
   (обычно включён по умолчанию).
4. Теперь GPU-машина доступна по стабильному имени вида
   `gaming-pc.tail1234.ts.net` (видно в админке или `tailscale status`),
   с любой сети и из Docker-контейнеров.

Проверка с Mac:
```bash
curl http://gaming-pc.tail1234.ts.net:11434/api/version
```

> Файрвол из шага 1.3 для Tailscale-трафика: Windows обычно пропускает трафик
> tailscale-интерфейса автоматически; если нет — добавь правило для подсети
> `100.64.0.0/10`.

---

## Часть 3. Mac — конфигурация проекта

### 3.1. Создать .env

```bash
cd ~/projects/AI_agents_enterprise
cp .env.example .env
```

### 3.2. Прописать в .env

```dotenv
# адрес GPU-машины — ОДИН из вариантов:
WB_LOCAL_LLM_BASE_URL=http://gaming-pc.local:11434              # вариант A: mDNS (только LAN, не работает из docker compose)
# WB_LOCAL_LLM_BASE_URL=http://gaming-pc.tail1234.ts.net:11434  # вариант B: Tailscale (рекомендую)

WB_LOCAL_LLM_MODEL=qwen2.5:3b-instruct

# ключи провайдеров (любое подмножество; провайдер включается, когда ключ задан)
ANTHROPIC_API_KEY=sk-ant-...     # console.anthropic.com → API Keys
OPENAI_API_KEY=sk-...            # platform.openai.com → API Keys
DEEPSEEK_API_KEY=sk-...          # platform.deepseek.com
MOONSHOT_API_KEY=sk-...          # platform.moonshot.ai (Kimi)
```

После докачки `qwen3:14b` на 4090 — добавить:
```dotenv
WB_LOCAL_LLM_MODEL=qwen3:14b
WB_ROUTE_STANDARD_VIA_LOCAL=true   # standard-tier тоже пойдёт на 4090 (бесплатно)
```

> `.env` в .gitignore — ключи в репозиторий не попадут.

### 3.3. Запустить и проверить

```bash
# терминал 1: инфраструктура (нужен запущенный Docker Desktop)
make up        # postgres + qdrant + redis + api в контейнерах
# ИЛИ без Docker — только API-процесс:
make api

# терминал 2: проверки
curl -s localhost:8000/healthz/deps | python3 -m json.tool   # postgres/redis/qdrant: ok?
curl -s localhost:8000/v1/models | python3 -m json.tool      # какие провайдеры enabled

# живой вызов LLM (пойдёт на 4090):
curl -s -X POST localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Скажи привет одним словом"}],"complexity":"simple"}'

# агент с tool-вызовом:
curl -s -X POST localhost:8000/v1/agents/demo/run -H 'Content-Type: application/json' \
  -d '{"input":"сколько будет 23.5 * 17 - 4?"}' | python3 -m json.tool
```

---

## Troubleshooting

| Симптом | Причина / решение |
|---|---|
| `/v1/chat` с `complexity=simple` отвечает не с `"provider":"local"` | 4090 недоступна — роутер ушёл в fallback. Проверь `curl http://<адрес-4090>:11434/api/version` с Mac |
| `curl: Could not resolve host: gaming-pc.local` | mDNS не резолвится: проверь, что обе машины в одной сети/VLAN; либо переходи на Tailscale (Часть 2) |
| Работает `make api`, но не работает из `make up` | `.local` не резолвится внутри Linux-контейнеров. Используй Tailscale-имя в `WB_LOCAL_LLM_BASE_URL` |
| `ollama: connection refused` с Mac, но локально на GPU-машине работает | `OLLAMA_HOST=0.0.0.0` не применился (перезапусти Ollama целиком) или файрвол режет 11434 |
| Провайдер в `/v1/models` показан `disabled` | Ключ не подхватился: ключи читаются из окружения процесса; при `make api` поставь их в `.env` (pydantic-settings читает `.env` из корня) |
| Embeddings: 503 `ollama unreachable` при ingest | То же, что п.1 — недоступна 4090. Для работы без GPU: `WB_EMBEDDINGS_BACKEND=hash` (несемантический режим, только для отладки) |
