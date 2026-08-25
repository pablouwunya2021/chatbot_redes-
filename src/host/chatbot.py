"""
Chatbot host / MCP anfitrión.

A ChatSession is the "host" from the MCP architecture: it owns one client
connection per MCP server, aggregates all their tools, keeps the conversation
context, and routes each tool call the LLM requests to the right server.

Used by both front-ends (terminal CLI and web UI).
"""
from __future__ import annotations

import json
import os
from typing import Callable, Optional

import config
import llm
from logger import InteractionLogger
from mcp_client import MCPError, MCPServerConnection, connect


class ChatSession:
    def __init__(
        self,
        use_remote_pharmacy: bool = False,
        echo_log: bool = False,
        console=None,
        enable_llm: bool = True,
    ):
        self.logger = InteractionLogger(config.INTERACTION_LOG, echo=echo_log, console=console)
        self.console = console
        self.use_remote_pharmacy = use_remote_pharmacy
        self.connections: dict[str, MCPServerConnection] = {}
        # namespaced tool name ("server__tool") -> (connection, tool_def)
        self.tool_index: dict[str, tuple] = {}
        self.contents: list = []  # conversation context (requirement #2)
        self._tools = None  # Gemini tool declarations, built lazily

        self.enable_llm = enable_llm and bool(config.GEMINI_API_KEY)
        self._client = None
        if self.enable_llm:
            from google import genai

            self._client = genai.Client(api_key=config.GEMINI_API_KEY)

    # -- connection management ---------------------------------------------
    def connect_all(self, skip: Optional[set] = None) -> dict[str, str]:
        """Connect to every configured MCP server. Returns {name: status}."""
        skip = skip or set()
        status: dict[str, str] = {}
        for sdef in config.get_server_definitions(self.use_remote_pharmacy):
            name = sdef["name"]
            if name in skip:
                status[name] = "skipped"
                continue
            try:
                conn = connect(sdef, self.logger)
                self.connections[name] = conn
                for tool in conn.tools:
                    self.tool_index[f"{name}__{tool['name']}"] = (conn, tool)
                status[name] = f"ok ({len(conn.tools)} tools, {sdef['transport']})"
            except Exception as exc:  # keep going if one server is unavailable
                status[name] = f"FAILED: {exc}"
                self.logger.log("error", name, sdef.get("transport", "?"),
                                {"error": str(exc)})
        return status

    def close_all(self) -> None:
        for conn in self.connections.values():
            try:
                conn.close()
            except Exception:
                pass
        self.connections.clear()

    # -- tool routing -------------------------------------------------------
    def call_tool_direct(self, server: str, tool: str, arguments: dict) -> dict:
        """Invoke a tool directly (used by the /call command and for demos)."""
        conn = self.connections.get(server)
        if not conn:
            raise MCPError(f"Not connected to server '{server}'.")
        return conn.call_tool(tool, arguments)

    def _dispatch_tool(self, full_name: str, arguments: dict) -> tuple[str, bool]:
        """Callback used by the LLM loop: run one tool, return (text, is_error)."""
        entry = self.tool_index.get(full_name)
        if not entry:
            return (f"Unknown tool: {full_name}", True)
        conn, _tool_def = entry
        tool_name = full_name.split("__", 1)[1]
        try:
            result = conn.call_tool(tool_name, arguments)
        except MCPError as exc:
            return (str(exc), True)
        is_error = bool(result.get("isError"))
        # Flatten MCP content blocks into a single text string for the model.
        text = self._content_to_text(result)
        return (text, is_error)

    @staticmethod
    def _content_to_text(result: dict) -> str:
        parts = []
        for block in result.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
        if not parts and "structuredContent" in result:
            parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
        return "\n".join(parts) if parts else "(no content)"

    # -- conversation -------------------------------------------------------
    def chat(self, user_text: str, on_event: Optional[Callable] = None) -> str:
        """Handle one user message, keeping full context across calls."""
        if not self.enable_llm:
            raise RuntimeError(
                "LLM is disabled (no GEMINI_API_KEY). Use direct tool calls "
                "with the /call command, or set your API key in .env."
            )
        if self._tools is None:
            self._tools = llm.build_tools(self.tool_index)
        llm.append_user_text(self.contents, user_text)
        answer = llm.run_conversation_turn(
            client=self._client,
            model=config.GEMINI_MODEL,
            contents=self.contents,
            tools=self._tools,
            dispatch_tool=self._dispatch_tool,
            on_event=on_event,
        )
        return answer

    def reset_context(self) -> None:
        self.contents.clear()

    # -- introspection ------------------------------------------------------
    def list_tools(self) -> list[dict]:
        out = []
        for full_name, (_conn, tool) in self.tool_index.items():
            out.append({"name": full_name, "description": tool.get("description", "")})
        return out

    def server_summary(self) -> list[dict]:
        return [
            {
                "name": name,
                "transport": conn.transport.kind,
                "server_info": conn.server_info,
                "tool_count": len(conn.tools),
            }
            for name, conn in self.connections.items()
        ]
