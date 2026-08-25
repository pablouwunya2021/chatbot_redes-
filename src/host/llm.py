"""
LLM layer -- talks to the Google Gemini API and runs the tool-use loop.

The Google Gemini SDK (google-genai) is used ONLY to reach the model over its
HTTP API (requirement #1: "connect to an LLM at the API level"). The MCP
protocol is still hand-written elsewhere. Here we:

  * translate MCP tool definitions into Gemini "function declarations",
  * send the running conversation (requirement #2: context is the full
    `contents` list, preserved across turns), and
  * whenever the model emits a functionCall, run it against the right MCP
    server and feed the functionResponse back to the model.

Note: only the LLM SDK changed (Anthropic -> Gemini). MCP, its message framing
and the official Filesystem/Git servers are unchanged.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

SYSTEM_PROMPT = (
    "You are the assistant for FarmaValle, a pharmacy chain. You can hold a "
    "normal conversation and answer general questions from your own knowledge. "
    "You also have TOOLS provided through MCP servers:\n"
    "  - filesystem tools: read/write files inside a sandboxed workspace.\n"
    "  - git tools: stage, commit, view status/log of a repository.\n"
    "  - pharmacy tools: search products, get drug info, recommend OTC products "
    "from symptoms, check inventory and place orders.\n\n"
    "Use a tool whenever it is the reliable way to answer (file operations, git "
    "actions, anything about products, stock, prices or orders). Do not invent "
    "product data, stock levels, prices or order ids: get them from the tools. "
    "When giving health guidance, only discuss over-the-counter options and "
    "always remind the user to consult a professional for serious or persistent "
    "symptoms. Keep answers concise and in the user's language."
)

# JSON-Schema fields Gemini's function-declaration schema understands. Anything
# else in an MCP inputSchema (e.g. additionalProperties, $schema) is dropped.
_TYPE_MAP = {
    "object": "OBJECT", "array": "ARRAY", "string": "STRING",
    "integer": "INTEGER", "number": "NUMBER", "boolean": "BOOLEAN",
}


def _convert_schema(schema: dict) -> dict:
    """Convert an MCP JSON-Schema into Gemini's (OpenAPI-subset) Schema dict."""
    out: dict[str, Any] = {}
    t = schema.get("type")
    if isinstance(t, str):
        out["type"] = _TYPE_MAP.get(t.lower(), "STRING")
    if "description" in schema:
        out["description"] = schema["description"]
    if "enum" in schema:
        out["enum"] = [str(v) for v in schema["enum"]]
    if "properties" in schema:
        out["properties"] = {k: _convert_schema(v) for k, v in schema["properties"].items()}
    if "required" in schema:
        out["required"] = schema["required"]
    if "items" in schema:
        out["items"] = _convert_schema(schema["items"])
    return out


def build_tools(tool_index: dict[str, tuple]):
    """Build the Gemini `Tool` list from the host's namespaced tool index."""
    from google.genai import types

    declarations = []
    for full_name, (_conn, tool_def) in tool_index.items():
        schema = tool_def.get("inputSchema") or {}
        params = _convert_schema(schema)
        # A function with no properties must declare no parameters at all.
        if not params.get("properties"):
            params = None
        declarations.append(
            types.FunctionDeclaration(
                name=full_name,
                description=(tool_def.get("description") or "")[:1000],
                parameters=params,
            )
        )
    return [types.Tool(function_declarations=declarations)]


def make_config(tools):
    from google.genai import types

    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools,
        # We resolve tool calls ourselves against MCP; disable auto-calling.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def append_user_text(contents: list, text: str) -> None:
    from google.genai import types

    contents.append(types.Content(role="user", parts=[types.Part(text=text)]))


def run_conversation_turn(
    client: Any,
    model: str,
    contents: list,
    tools: list,
    dispatch_tool: Callable[[str, dict], tuple],
    on_event: Optional[Callable[[str, dict], None]] = None,
    max_tool_rounds: int = 8,
) -> str:
    """Drive one user turn to completion, resolving any function calls.

    `contents` is mutated in place so the caller keeps the full context.
    `dispatch_tool(name, args)` must return (result_text, is_error).
    Returns the model's final natural-language answer.
    """
    from google.genai import types

    config = make_config(tools)

    def emit(kind: str, payload: dict) -> None:
        if on_event:
            on_event(kind, payload)

    final_text_parts: list[str] = []

    for _ in range(max_tool_rounds):
        response = client.models.generate_content(
            model=model, contents=contents, config=config
        )

        if not response.candidates:
            break
        content = response.candidates[0].content
        parts = list(content.parts or [])
        contents.append(content)  # record the model turn (context)

        function_calls = []
        for part in parts:
            if getattr(part, "text", None):
                final_text_parts.append(part.text)
                emit("assistant_text", {"text": part.text})
            if getattr(part, "function_call", None):
                function_calls.append(part.function_call)

        if not function_calls:
            break

        # Execute every requested tool; send the results back in one turn.
        response_parts = []
        for fc in function_calls:
            args = dict(fc.args) if fc.args else {}
            emit("tool_call", {"name": fc.name, "input": args})
            result_text, is_error = dispatch_tool(fc.name, args)
            emit("tool_result", {"name": fc.name, "is_error": is_error, "text": result_text})
            response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result_text, "isError": is_error},
                )
            )
        contents.append(types.Content(role="user", parts=response_parts))
    else:
        emit("info", {"text": "Reached max tool rounds."})

    return "\n".join(t for t in final_text_parts if t.strip()).strip()
