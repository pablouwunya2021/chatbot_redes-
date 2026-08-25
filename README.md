# FarmaValle — MCP Chatbot (UVG · CC3067 Redes · Project 1)

A command-line **and** web chatbot that acts as an **MCP host (anfitrión)**,
connecting an LLM to several **MCP servers**. The whole **Model Context
Protocol is implemented by hand in raw JSON-RPC 2.0** — no MCP SDK, no FastMCP.

The chatbot connects to:

| Server | Role | Transport |
|--------|------|-----------|
| **Filesystem** (official Anthropic) | read/write files in a sandbox | stdio |
| **Git** (official Anthropic) | stage / commit / log a repository | stdio |
| **Pharmacy** (custom, this repo) | pharmacy-chain business tools | stdio (local) **and** HTTP (remote/cloud) |

The custom server models a **pharmacy chain ("FarmaValle")**: a customer
describes symptoms, the bot recommends over-the-counter products, checks
inventory and places an order.

---

## Features (mapped to the assignment)

- **General chat via the LLM API** — answers from the model's own knowledge
  (`src/host/llm.py`, Google Gemini API).
- **Conversation context** — the full `messages` history is preserved across
  turns, so follow-up questions ("…and when was he born?") resolve correctly.
- **Interaction log** — every JSON-RPC request/response with every MCP server
  is appended to `logs/mcp_interactions.jsonl` and viewable with `/log`
  (terminal) or the live **MCP Activity Log** panel (web).
- **Official local servers** — Filesystem + Git, with a demo that creates a
  repo, writes a README, stages and commits it (`src/demo_git_filesystem.py`).
- **Custom local MCP server** — the pharmacy server over stdio
  (`src/servers/pharmacy/server_stdio.py`).
- **Custom remote MCP server** — the *same* server over HTTP, ready for Google
  Cloud Run / Cloudflare (`src/servers/pharmacy/server_http.py`, `deploy/`).
- **Wireshark analysis** — reproducible capture + JSON-RPC/OSI-layer analysis
  (`docs/wireshark/WIRESHARK_ANALYSIS.md`).
- **UI (15% extra)** — a Rich terminal UI **and** a FastAPI web chat, both HCI
  oriented (`src/host/cli.py`, `src/ui/web/`).

> **Note (real-world finding).** The current official `mcp-server-git` no
> longer ships a `git_init` tool, so repository *creation* uses a plain
> `git init`; every other git action goes through the official Git MCP server.

---

## Requirements

- **Python 3.10+**
- **Node.js + npx** (runs the official Filesystem server)
- **uv / uvx** (runs the official Git server) — https://docs.astral.sh/uv/
- A **Google Gemini API key** (free from Google AI Studio, no card needed)

---

## Installation

```bash
git clone <your-repo-url>
cd chatbot_redes-

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit .env and paste your API key
```

`.env` keys:

```ini
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.0-flash
FILESYSTEM_ROOT=./workspace
PHARMACY_REMOTE_URL=http://127.0.0.1:8000/mcp
PHARMACY_API_KEY=demo-key
```

---

## Usage

### Terminal chatbot

```bash
python src/host/cli.py                 # uses the LOCAL pharmacy server (stdio)
python src/host/cli.py --remote        # uses the REMOTE pharmacy server (HTTP)
python src/host/cli.py --echo-log      # also print every JSON-RPC message live
```

Slash commands: `/help`, `/servers`, `/tools`, `/log [N]`,
`/call <server> <tool> {json}`, `/reset`, `/quit`.

Example conversation:

```
you › I have a fever and a headache, what can I take?
  → tool pharmacy__recommend_for_symptoms {"symptoms":["fever","headache"]}
bot › For a fever and headache you can consider acetaminophen (Tylenol) …
you › is that one in stock in Zona 10?
  → tool pharmacy__check_inventory {"medication_id":"MED-001","store_id":"S1"}
bot › Yes — FarmaValle Zona 10 has 120 units in stock …
```

### Web chatbot

```bash
python src/ui/web/app.py               # open http://127.0.0.1:8080
REMOTE_PHARMACY=1 python src/ui/web/app.py   # use the remote pharmacy server
```

### Demos (no API key / no LLM credits needed)

```bash
python src/demo_git_filesystem.py      # Filesystem + Git official servers (req #4)
# remote session (req #6/#7): run the server, then the driver
PORT=8000 python src/servers/pharmacy/server_http.py &
python src/demo_remote_session.py
```

### Inspect the pharmacy server by hand

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 | python src/servers/pharmacy/server_stdio.py
```

---

## Project layout

```
src/
  host/                 the chatbot host (MCP anfitrión)
    mcp_client.py       hand-written JSON-RPC MCP client (stdio + HTTP)
    chatbot.py          session: connects servers, routes tools, keeps context
    llm.py              Google Gemini API + tool-use loop
    logger.py           interaction log (requirement #3)
    config.py           MCP server registry
    cli.py              terminal UI (15% extra)
  servers/pharmacy/     custom MCP server (industry use case)
    core.py             tools + hand-written JSON-RPC dispatcher
    data.py             catalogue / inventory dataset
    server_stdio.py     LOCAL transport  (requirement #5)
    server_http.py      REMOTE transport (requirement #6)
  ui/web/               FastAPI web chat (15% extra)
  demo_git_filesystem.py
  demo_remote_session.py
deploy/                 Dockerfile + Cloud Run / Cloudflare guide
docs/                   report, server spec, wireshark analysis
logs/                   JSON-Lines interaction logs
```

Full documentation: [`docs/SERVER_SPEC.md`](docs/SERVER_SPEC.md) (server spec) ·
[`docs/REPORTE.md`](docs/REPORTE.md) (report) ·
[`docs/wireshark/WIRESHARK_ANALYSIS.md`](docs/wireshark/WIRESHARK_ANALYSIS.md).

---

## Academic integrity

The MCP protocol is implemented from the JSON-RPC 2.0 and MCP specifications
(no MCP SDK). The Google Gemini SDK is used only to reach the LLM over its HTTP
API. Third-party references are cited in code comments where used.
