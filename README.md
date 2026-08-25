# FarmaValle — Chatbot MCP

Proyecto 1 · CC3067 Redes · UVG — **Pablo Cabrera (231156)**

Un chatbot (anfitrión) que conecta un LLM (Google Gemini) con varios
**servidores MCP**. El protocolo **MCP se implementó a mano en JSON-RPC 2.0**,
sin SDKs de MCP ni FastMCP.

Servidores que usa el chatbot:

- **Filesystem** y **Git** (oficiales de Anthropic) — leer/escribir archivos y
  manejar un repositorio.
- **Pharmacy** (propio) — cadena de farmacias: recomienda productos según
  síntomas, consulta inventario y hace pedidos. Corre **local (stdio)** y
  **remoto (HTTP, en Google Cloud Run)**.

## Requisitos

- Python 3.10+, Node.js (`npx`) y `uv`/`uvx`
- Una API key de Google Gemini (gratis en https://aistudio.google.com/apikey)

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # pega tu GEMINI_API_KEY en .env
```

## Uso

```bash
python src/host/cli.py            # chatbot en terminal (farmacia local)
python src/host/cli.py --remote   # usa el servidor de farmacia en la nube
python src/ui/web/app.py          # interfaz web en http://127.0.0.1:8080
```

Comandos dentro del chat: `/tools`, `/servers`, `/log`, `/reset`, `/quit`.

## Estructura

```
src/host/       anfitrión: cliente MCP (mcp_client.py), LLM (llm.py), chatbot.py
src/servers/    servidor de farmacia (stdio + HTTP)
src/ui/web/     interfaz web
deploy/         Dockerfile y guía de despliegue en Cloud Run
docs/           reporte, especificación y análisis de Wireshark
```

Más detalle en [`docs/REPORTE.md`](docs/REPORTE.md).
