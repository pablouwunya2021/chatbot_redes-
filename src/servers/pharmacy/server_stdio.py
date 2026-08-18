#!/usr/bin/env python3
"""
Pharmacy MCP server -- LOCAL (stdio) transport.  Requirement #5.

Reads newline-delimited JSON-RPC 2.0 messages from stdin and writes the
responses to stdout, one JSON object per line. This is the exact framing the
official MCP stdio servers use, implemented here by hand (no SDK).

Run standalone for a quick manual test:
    python src/servers/pharmacy/server_stdio.py
    {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
    {"jsonrpc":"2.0","id":2,"method":"tools/list"}
"""
import json
import os
import sys

# Allow running as a plain script: make sibling modules importable.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402


def main() -> None:
    # Line-buffered stdio. All human-readable logging must go to stderr so it
    # never corrupts the JSON-RPC stream on stdout.
    print("pharmacy-mcp (stdio) ready", file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            # -32700 Parse error (id unknown -> null)
            sys.stdout.write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": f"Parse error: {exc}"}}
                )
                + "\n"
            )
            sys.stdout.flush()
            continue

        response = core.handle_message(message)
        if response is not None:  # notifications get no reply
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
