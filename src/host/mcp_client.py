"""
Manual MCP client  ---  NO SDK, NO FastMCP.

This module implements, by hand, the parts of the Model Context Protocol the
chatbot host needs to drive an MCP server:

    * JSON-RPC 2.0 message framing (id counter, request/response/notification)
    * the MCP lifecycle:   initialize  ->  notifications/initialized
    * discovery:           tools/list
    * invocation:          tools/call

Two transports are provided, both speaking the SAME JSON-RPC messages:

    StdioTransport  -- launches the server as a child process and exchanges
                       newline-delimited JSON over stdin/stdout. This is the
                       transport used by the official Filesystem/Git servers
                       and by our LOCAL pharmacy server.

    HttpTransport   -- POSTs each JSON-RPC message to an HTTP endpoint. This is
                       the transport used by our REMOTE (cloud) pharmacy server.

Reference: JSON-RPC 2.0 (https://www.jsonrpc.org/specification) and the MCP
specification (https://modelcontextprotocol.io/specification/2025-06-18).
"""
from __future__ import annotations

import json
import subprocess
import threading
import urllib.error
import urllib.request
from typing import Any, Optional

from logger import InteractionLogger

# Protocol version this client requests during initialize. The server may
# answer with a different (compatible) version, which we accept.
PROTOCOL_VERSION = "2025-06-18"

CLIENT_INFO = {"name": "uvg-redes-chatbot", "version": "1.0.0"}


class MCPError(Exception):
    """Raised when a JSON-RPC call returns an error or a transport fails."""


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------
class StdioTransport:
    """Speak JSON-RPC 2.0 over a child process' stdin/stdout.

    MCP's stdio transport frames each message as a single line of UTF-8 JSON
    terminated by '\\n' (messages must not contain embedded newlines).
    """

    kind = "stdio"

    def __init__(self, command: list[str], env: Optional[dict] = None):
        self.command = command
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,  # line buffered
            env=env,
        )
        # Drain stderr in the background so the server never blocks on a full
        # pipe. Server diagnostics are collected for debugging.
        self.stderr_lines: list[str] = []
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self.stderr_lines.append(line.rstrip("\n"))

    def send(self, message: dict) -> None:
        assert self._proc.stdin is not None
        if self._proc.poll() is not None:
            raise MCPError(
                f"server process exited (code {self._proc.returncode}). "
                f"stderr: {' | '.join(self.stderr_lines[-5:])}"
            )
        self._proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

    def receive(self) -> dict:
        """Block until the next complete JSON message arrives from the server."""
        assert self._proc.stdout is not None
        line = self._proc.stdout.readline()
        if line == "":
            raise MCPError(
                "server closed the connection. "
                f"stderr: {' | '.join(self.stderr_lines[-5:])}"
            )
        line = line.strip()
        if not line:
            return self.receive()  # skip blank keep-alive lines
        return json.loads(line)

    def close(self) -> None:
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass


class HttpTransport:
    """Speak JSON-RPC 2.0 over HTTP POST (MCP 'Streamable HTTP' transport).

    Each request is POSTed to the endpoint. The server may answer with either
    a plain application/json body or a text/event-stream (SSE); both are
    handled. The session id returned on `initialize` (if any) is echoed back
    on subsequent requests via the `Mcp-Session-Id` header.
    """

    kind = "http"

    def __init__(self, url: str, headers: Optional[dict] = None, timeout: float = 60.0):
        self.url = url
        self.extra_headers = headers or {}
        self.timeout = timeout
        self.session_id: Optional[str] = None
        # Queue of already-received messages (HTTP is strictly request/reply,
        # so at most one message is produced per send()).
        self._pending: list[dict] = []

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        h.update(self.extra_headers)
        return h

    def send(self, message: dict) -> None:
        data = json.dumps(message, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # Capture a session id handed out on initialize.
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                body = resp.read().decode("utf-8")
                content_type = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:  # 4xx / 5xx
            detail = exc.read().decode("utf-8", "replace")
            raise MCPError(f"HTTP {exc.code} from server: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MCPError(f"cannot reach remote MCP server at {self.url}: {exc}") from exc

        # A notification (no id) yields an empty 202 body: nothing to queue.
        if not body.strip():
            return
        if "text/event-stream" in content_type:
            for msg in self._parse_sse(body):
                self._pending.append(msg)
        else:
            self._pending.append(json.loads(body))

    @staticmethod
    def _parse_sse(body: str) -> list[dict]:
        """Extract JSON payloads from Server-Sent-Events `data:` lines."""
        messages = []
        for block in body.split("\n\n"):
            data = "".join(
                line[5:].lstrip()
                for line in block.splitlines()
                if line.startswith("data:")
            )
            if data.strip():
                messages.append(json.loads(data))
        return messages

    def receive(self) -> dict:
        if not self._pending:
            raise MCPError("no response received from remote server")
        return self._pending.pop(0)

    def close(self) -> None:
        self._pending.clear()


# ---------------------------------------------------------------------------
# MCP connection (lifecycle + discovery + invocation on top of a transport)
# ---------------------------------------------------------------------------
class MCPServerConnection:
    def __init__(self, name: str, transport: Any, logger: InteractionLogger):
        self.name = name
        self.transport = transport
        self.logger = logger
        self._id = 0
        self.server_info: dict = {}
        self.capabilities: dict = {}
        self.tools: list[dict] = []

    # -- low level ----------------------------------------------------------
    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _request(self, method: str, params: Optional[dict] = None) -> Any:
        """Send a JSON-RPC request and return its `result`, matching by id."""
        rid = self._next_id()
        message = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            message["params"] = params

        self.logger.log("request", self.name, self.transport.kind, message)
        self.transport.send(message)

        # Read messages until we get the response with our id. Any notification
        # the server emits in between is logged and skipped.
        while True:
            reply = self.transport.receive()
            if reply.get("id") == rid:
                self.logger.log(
                    "error" if "error" in reply else "response",
                    self.name,
                    self.transport.kind,
                    reply,
                )
                if "error" in reply:
                    err = reply["error"]
                    raise MCPError(
                        f"{self.name}: JSON-RPC error {err.get('code')}: "
                        f"{err.get('message')}"
                    )
                return reply.get("result")
            # Out-of-band message (server notification / log): record it.
            self.logger.log("notification", self.name, self.transport.kind, reply)

    def _notify(self, method: str, params: Optional[dict] = None) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.logger.log("notification", self.name, self.transport.kind, message)
        self.transport.send(message)

    # -- MCP lifecycle ------------------------------------------------------
    def initialize(self) -> None:
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": CLIENT_INFO,
            },
        )
        self.server_info = result.get("serverInfo", {})
        self.capabilities = result.get("capabilities", {})
        # Handshake completion notification (required by MCP).
        self._notify("notifications/initialized")

    def list_tools(self) -> list[dict]:
        result = self._request("tools/list")
        self.tools = result.get("tools", [])
        return self.tools

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        return self._request("tools/call", {"name": tool_name, "arguments": arguments})

    def close(self) -> None:
        self.transport.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def connect(server_def: dict, logger: InteractionLogger) -> MCPServerConnection:
    """Build a connection from a server definition (see host/config.py)."""
    transport_kind = server_def["transport"]
    if transport_kind == "stdio":
        transport: Any = StdioTransport(server_def["command"], env=server_def.get("env"))
    elif transport_kind == "http":
        transport = HttpTransport(server_def["url"], headers=server_def.get("headers"))
    else:
        raise ValueError(f"unknown transport: {transport_kind}")

    conn = MCPServerConnection(server_def["name"], transport, logger)
    conn.initialize()
    conn.list_tools()
    return conn
