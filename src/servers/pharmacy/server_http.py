#!/usr/bin/env python3
"""
Pharmacy MCP server -- REMOTE (HTTP) transport.  Requirement #6.

Exposes the SAME JSON-RPC 2.0 / MCP surface as server_stdio.py, but over HTTP
so it can be deployed to a cloud service (e.g. Google Cloud Run). The chatbot
host reaches it with the HttpTransport and uses it exactly like the local one.

Endpoint:
    POST /mcp        -> body is one JSON-RPC message; reply is one JSON-RPC
                        message (application/json). Notifications return 202.
    GET  /healthz    -> liveness probe for the cloud platform.

We use FastAPI/uvicorn only as a plain HTTP server. The MCP protocol itself is
still hand-written in core.py (no MCP SDK).

Run locally:
    uvicorn server_http:app --host 0.0.0.0 --port 8000
    # or simply:  python src/servers/pharmacy/server_http.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402

from fastapi import FastAPI, Request, Response  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

app = FastAPI(title="Pharmacy MCP Server", version=core.SERVER_INFO["version"])

# Optional shared-secret check (set PHARMACY_API_KEY in the environment).
EXPECTED_API_KEY = os.getenv("PHARMACY_API_KEY", "")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "server": core.SERVER_INFO}


@app.get("/")
def root() -> dict:
    return {
        "service": "pharmacy-mcp",
        "transport": "http",
        "endpoint": "/mcp",
        "protocol": "JSON-RPC 2.0 / MCP " + core.PROTOCOL_VERSION,
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> Response:
    # Lightweight auth (demonstrates header-based access control for a remote
    # server). Disabled if no key is configured.
    if EXPECTED_API_KEY:
        if request.headers.get("X-API-Key") != EXPECTED_API_KEY:
            return JSONResponse(
                status_code=401,
                content={"jsonrpc": "2.0", "id": None,
                         "error": {"code": -32001, "message": "Unauthorized"}},
            )

    try:
        message = await request.json()
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": f"Parse error: {exc}"}},
        )

    reply = core.handle_message(message)

    # Notifications produce no reply -> 202 Accepted with empty body.
    if reply is None:
        return Response(status_code=202)

    headers = {}
    # Hand out a session id on initialize (echoed by the client afterwards).
    if message.get("method") == "initialize":
        headers["Mcp-Session-Id"] = uuid.uuid4().hex
    return JSONResponse(content=reply, headers=headers)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))  # Cloud Run injects $PORT
    uvicorn.run(app, host="0.0.0.0", port=port)
