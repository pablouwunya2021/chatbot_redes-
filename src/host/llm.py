"""
LLM layer -- talks to the Anthropic Messages API and runs the tool-use loop.

The Anthropic SDK is used ONLY to reach the model over its HTTP API
(requirement #1: "connect to an LLM at the API level"). The MCP protocol is
still hand-written elsewhere. Here we:

  * translate MCP tool definitions into the Anthropic `tools` format,
  * send the running conversation (requirement #2: context is the full
    `messages` list, preserved across turns), and
  * whenever the model asks to use a tool, call back into the host to run it
    against the right MCP server, then feed the result back to the model.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import anthropic

SYSTEM_PROMPT = (
    "You are the assistant for FarmaValle, a pharmacy chain. You can hold a "
    "normal conversation and answer general questions from your own knowledge. "
    "You also have TOOLS provided through MCP servers:\n"
    "  - filesystem tools: read/write files inside a sandboxed workspace.\n"
    "  - git tools: initialise repos, stage, commit, view status/log.\n"
    "  - pharmacy tools: search products, get drug info, recommend OTC products "
    "from symptoms, check inventory and place orders.\n\n"
    "Use a tool whenever it is the reliable way to answer (file operations, git "
    "actions, anything about products, stock, prices or orders). Do not invent "
    "product data, stock levels, prices or order ids: get them from the tools. "
    "When giving health guidance, only discuss over-the-counter options and "
    "always remind the user to consult a professional for serious or persistent "
    "symptoms. Keep answers concise and in the user's language."
)


def mcp_tools_to_anthropic(tool_index: dict[str, tuple]) -> list[dict]:
    """Convert the host's tool index into the Anthropic `tools` array.

    tool_index maps a namespaced name ("server__tool") to
    (connection, mcp_tool_definition).
    """
    tools = []
    for full_name, (_conn, tool_def) in tool_index.items():
        schema = tool_def.get("inputSchema") or {"type": "object", "properties": {}}
        tools.append(
            {
                "name": full_name,
                "description": tool_def.get("description", "")[:1000],
                "input_schema": schema,
            }
        )
    return tools


def run_conversation_turn(
    client: anthropic.Anthropic,
    model: str,
    messages: list[dict],
    tools: list[dict],
    dispatch_tool: Callable[[str, dict], tuple],
    on_event: Optional[Callable[[str, dict], None]] = None,
    max_tokens: int = 1024,
    max_tool_rounds: int = 8,
) -> str:
    """Drive one user turn to completion, resolving any tool calls.

    `messages` is mutated in place so the caller keeps the full context.
    `dispatch_tool(name, input)` must return (result_text, is_error).
    Returns the model's final natural-language answer.
    """

    def emit(kind: str, payload: dict) -> None:
        if on_event:
            on_event(kind, payload)

    final_text_parts: list[str] = []

    for _ in range(max_tool_rounds):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # Rebuild the assistant message as plain dicts (serialisable + reusable).
        assistant_content: list[dict] = []
        tool_uses: list[dict] = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
                if block.text.strip():
                    final_text_parts.append(block.text)
                    emit("assistant_text", {"text": block.text})
            elif block.type == "tool_use":
                tu = {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                assistant_content.append(tu)
                tool_uses.append(tu)
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason != "tool_use":
            break

        # Run every requested tool and return the results in one user message.
        tool_results = []
        for tu in tool_uses:
            emit("tool_call", {"name": tu["name"], "input": tu["input"]})
            result_text, is_error = dispatch_tool(tu["name"], tu["input"])
            emit("tool_result", {"name": tu["name"], "is_error": is_error, "text": result_text})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": result_text,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})
        # loop again so the model can use the tool output
    else:
        emit("info", {"text": "Reached max tool rounds."})

    return "\n".join(final_text_parts).strip()
