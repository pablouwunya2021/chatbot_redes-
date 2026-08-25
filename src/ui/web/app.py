#!/usr/bin/env python3
"""
Web chatbot (front-end #2, part of the 15% UI extra).

A small FastAPI app that wraps the same ChatSession host used by the terminal
UI. It serves a single-page chat and a JSON API. The MCP servers are connected
once at startup and shared across requests.

Run:
    python src/ui/web/app.py
    # then open http://127.0.0.1:8080

Flags via environment:
    REMOTE_PHARMACY=1   use the remote (HTTP) pharmacy server.
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Make the host package importable.
HOST_DIR = Path(__file__).resolve().parents[2] / "host"
sys.path.insert(0, str(HOST_DIR))

from chatbot import ChatSession  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
SESSION: ChatSession | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global SESSION
    use_remote = os.getenv("REMOTE_PHARMACY", "") in ("1", "true", "yes")
    SESSION = ChatSession(use_remote_pharmacy=use_remote)
    status = SESSION.connect_all()
    print("MCP servers:", status)
    yield
    SESSION.close_all()


app = FastAPI(title="FarmaValle Web Chatbot", lifespan=lifespan)


class ChatIn(BaseModel):
    message: str


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/chat")
def chat(body: ChatIn):
    assert SESSION is not None
    if not SESSION.enable_llm:
        return JSONResponse(
            status_code=503,
            content={"error": "LLM disabled: set GEMINI_API_KEY in .env to chat. "
                              "Tool inspection endpoints still work."},
        )
    events: list[dict] = []
    answer = SESSION.chat(body.message, on_event=lambda k, p: events.append({"kind": k, **p}))
    return {"answer": answer, "events": events}


@app.get("/api/servers")
def servers():
    assert SESSION is not None
    return {"servers": SESSION.server_summary(), "llm_enabled": SESSION.enable_llm}


@app.get("/api/tools")
def tools():
    assert SESSION is not None
    return {"tools": SESSION.list_tools()}


@app.get("/api/log")
def log(n: int = 30):
    assert SESSION is not None
    return {"entries": SESSION.logger.read_entries()[-n:]}


@app.post("/api/reset")
def reset():
    assert SESSION is not None
    SESSION.reset_context()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("WEB_PORT", "8080")))
