# Environment setup (ADR-009: the service on one host, a GPU box for inference)

A one-time, step-by-step walkthrough of what to configure and where. The
topology assumes two machines — the one running the platform, and a separate box
with the GPU serving local models. If you only have one machine, everything still
works: point `WB_LOCAL_LLM_BASE_URL` at `localhost` and skip Parts 1 and 2.

Throughout, `gpu-box` stands for the hostname of your GPU machine.

---

## Part 1. The GPU machine — expose Ollama to the network

### 1.1. Check that Ollama is installed

Open a terminal (PowerShell on Windows) and run:

```
ollama --version
```

If the command is missing, install it from https://ollama.com/download.

### 1.2. Make Ollama listen on the network rather than only on localhost

By default Ollama accepts requests only from the machine it runs on. It needs
`OLLAMA_HOST=0.0.0.0`.

**Windows:**
1. `Win + R` → `sysdm.cpl` → the *Advanced* tab → *Environment Variables*.
2. Under *User variables* → *New*:
   - Name: `OLLAMA_HOST`
   - Value: `0.0.0.0`
3. Quit Ollama completely (tray icon → Quit) and start it again.

**Linux (systemd):**
```bash
sudo systemctl edit ollama
# add to the file that opens:
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0"
sudo systemctl restart ollama
```

### 1.3. Open port 11434 in the firewall — for the local network only

**Windows (PowerShell as administrator):**
```powershell
New-NetFirewallRule -DisplayName "Ollama LAN" -Direction Inbound -Protocol TCP `
  -LocalPort 11434 -RemoteAddress LocalSubnet -Action Allow
```

`-RemoteAddress LocalSubnet` is the important part: the port is reachable from
the local network only, never from the internet. Ollama has no authentication of
its own.

**Linux (ufw):** `sudo ufw allow from 192.168.0.0/16 to any port 11434`

### 1.4. Pull the models

```
ollama pull nomic-embed-text        # embeddings for RAG (~270 MB)
ollama pull qwen2.5:3b-instruct     # the simple tier
# later, for a free standard tier (recommended):
ollama pull qwen3:14b
```

> If you already have Qwen weights that did not come from Ollama (raw HuggingFace
> files, LM Studio), Ollama still needs its own `pull` — it keeps models in its
> own format. Alternatively run LM Studio Server or vLLM instead; both expose an
> OpenAI-compatible API, and Part 3 just points at their address and port.

### 1.5. Find the machine's name

```
hostname
```

If that prints `gpu-box`, the address from the other machine is
`http://gpu-box.local:11434`.

---

## Part 2 (recommended). Tailscale — a stable name without a static IP

`*.local` only works inside one LAN, and it does not resolve inside Docker
containers. Tailscale solves both. It is free and takes about ten minutes.

1. https://tailscale.com/download → install it **on both machines**.
2. Log in with the **same** account on both (Google or GitHub).
3. In the admin panel at https://login.tailscale.com/admin/dns, enable
   **MagicDNS** (usually on by default).
4. The GPU machine is now reachable at a stable name like
   `gpu-box.tail1234.ts.net` — visible in the admin panel or via
   `tailscale status` — from any network and from inside Docker containers.

Check it from the other machine:

```bash
curl http://gpu-box.tail1234.ts.net:11434/api/version
```

> About the firewall rule from 1.3: Windows normally lets traffic on the
> Tailscale interface through automatically. If it does not, add a rule for the
> `100.64.0.0/10` subnet.

---

## Part 3. The platform host — project configuration

### 3.1. Create .env

```bash
cd /path/to/AI-agents-enterprise
cp .env.example .env
```

### 3.2. Fill it in

```dotenv
# the GPU machine's address — pick ONE:
WB_LOCAL_LLM_BASE_URL=http://gpu-box.local:11434              # option A: mDNS (LAN only, does not work from docker compose)
# WB_LOCAL_LLM_BASE_URL=http://gpu-box.tail1234.ts.net:11434  # option B: Tailscale (recommended)

WB_LOCAL_LLM_MODEL=qwen2.5:3b-instruct

# provider keys — any subset; a provider is enabled once its key is set
ANTHROPIC_API_KEY=sk-ant-...     # console.anthropic.com → API Keys
OPENAI_API_KEY=sk-...            # platform.openai.com → API Keys
DEEPSEEK_API_KEY=sk-...          # platform.deepseek.com
MOONSHOT_API_KEY=sk-...          # platform.moonshot.ai (Kimi)
```

Once `qwen3:14b` has finished downloading on the GPU box, add:

```dotenv
WB_LOCAL_LLM_MODEL=qwen3:14b
WB_ROUTE_STANDARD_VIA_LOCAL=true   # send the standard tier to the GPU box too — free
```

> `.env` is in `.gitignore`, so keys never reach the repository.

### 3.3. Run it and check

```bash
# terminal 1: infrastructure (needs Docker Desktop running)
make up        # postgres + qdrant + redis + api, in containers
# OR without Docker — just the API process:
make api

# terminal 2: checks
curl -s localhost:8000/healthz/deps | python3 -m json.tool   # postgres/redis/qdrant: ok?
curl -s localhost:8000/v1/models | python3 -m json.tool      # which providers are enabled

# a live LLM call — this one goes to the GPU box:
curl -s -X POST localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Say hello in one word"}],"complexity":"simple"}'

# an agent making a tool call:
curl -s -X POST localhost:8000/v1/agents/demo/run -H 'Content-Type: application/json' \
  -d '{"input":"what is 23.5 * 17 - 4?"}' | python3 -m json.tool
```

---

## Part 4 (optional). A real MCP server, and the Playwright e2e

Both are off by default — the demo runs without them.

### 4.1. A real MCP server for Deep Research

By default Deep Research uses in-process corpus connectors. To take its tools
from an **actual MCP server** over stdio — behind the same allowlist and audit
log — set the command that starts it in `.env`:

```dotenv
# option A: the project's bundled server (re-serves the same corpus over real MCP)
WB_MCP_SERVER_COMMAND=python -m workbench_toolgateway.mcp_server
# option B: a third-party MCP server, e.g. fetch (needs uvx installed)
# WB_MCP_SERVER_COMMAND=uvx mcp-server-fetch
```

To see what the live server exposes:

```bash
curl -s localhost:8000/v1/apps/research/mcp/tools | python3 -m json.tool
```

> A third-party server (option B) exposes its own tools, so the source text in
> the report may come back empty — the report pulls bodies from the local corpus.
> Source names, URLs and the tool trace are still filled in correctly.

### 4.2. Playwright — a real browser in Computer-Use QA

The QA module runs against a fast virtual UI by default. To run the same
scenarios in **real headless Chromium**:

```bash
uv run playwright install chromium   # once — downloads the browser (~150 MB)
make e2e                             # = uv run pytest -m playwright
```

`make test` does not touch the browser tests — they are deselected by default —
so an ordinary run needs no Chromium.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/v1/chat` with `complexity=simple` does not answer with `"provider":"local"` | The GPU box is unreachable and the router fell back. Check `curl http://<gpu-box-address>:11434/api/version` from the platform host |
| `curl: Could not resolve host: gpu-box.local` | mDNS is not resolving: make sure both machines are on the same network/VLAN, or switch to Tailscale (Part 2) |
| Works under `make api` but not under `make up` | `.local` does not resolve inside Linux containers. Use the Tailscale name in `WB_LOCAL_LLM_BASE_URL` |
| `ollama: connection refused` from the platform host, though it works locally on the GPU box | `OLLAMA_HOST=0.0.0.0` did not take effect (restart Ollama completely), or the firewall is blocking 11434 |
| A provider shows as `disabled` in `/v1/models` | The key was not picked up. Keys are read from the process environment; under `make api`, put them in `.env` (pydantic-settings reads `.env` from the repository root) |
| Embeddings return 503 `ollama unreachable` during ingest | Same as the first row — the GPU box is unreachable. To work without a GPU: `WB_EMBEDDINGS_BACKEND=hash`, a non-semantic mode intended only for debugging |
