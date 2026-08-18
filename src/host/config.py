"""
Configuration for the chatbot host.

Defines WHICH MCP servers the chatbot connects to and HOW (transport,
command / URL, credentials). Everything is driven by environment variables
loaded from a local .env file.

Two transport types are used in this project:
  - "stdio": the server runs as a local child process; JSON-RPC messages are
             exchanged over its stdin/stdout (newline-delimited). Used by the
             official Filesystem and Git servers and by the LOCAL pharmacy
             server (project requirements #4 and #5).
  - "http" : the server runs remotely; JSON-RPC messages are POSTed over HTTP.
             Used by the REMOTE pharmacy server (requirement #6).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Project paths ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

# --- LLM settings -----------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# --- Filesystem sandbox -----------------------------------------------------
FILESYSTEM_ROOT = Path(
    os.getenv("FILESYSTEM_ROOT", str(PROJECT_ROOT / "workspace"))
).resolve()
FILESYSTEM_ROOT.mkdir(parents=True, exist_ok=True)

# --- Remote pharmacy server -------------------------------------------------
PHARMACY_REMOTE_URL = os.getenv("PHARMACY_REMOTE_URL", "http://127.0.0.1:8000/mcp")
PHARMACY_API_KEY = os.getenv("PHARMACY_API_KEY", "demo-key")

# Log file (JSON Lines) where every MCP request/response is appended.
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
INTERACTION_LOG = LOG_DIR / "mcp_interactions.jsonl"


def get_server_definitions(use_remote_pharmacy: bool = False) -> list[dict]:
    """Return the list of MCP servers the chatbot should connect to.

    Args:
        use_remote_pharmacy: if True, use the cloud (HTTP) pharmacy server
            instead of the local (stdio) one. This is how we demonstrate that
            the chatbot uses the remote server exactly like the local one
            (requirement #6).
    """
    python = sys.executable  # same interpreter running the host

    servers: list[dict] = [
        # ---- Requirement #4: official Filesystem MCP server (Node/npx) -----
        {
            "name": "filesystem",
            "transport": "stdio",
            "command": [
                "npx",
                "-y",
                "@modelcontextprotocol/server-filesystem",
                str(FILESYSTEM_ROOT),
            ],
            "description": "Official Anthropic filesystem server (sandboxed).",
        },
        # ---- Requirement #4: official Git MCP server (Python) --------------
        # Run with: uvx mcp-server-git   (or: pip install mcp-server-git)
        # No --repository is passed so the server starts unbound; each git tool
        # receives an explicit repo_path (e.g. a folder created via git_init),
        # which lets the demo create a brand-new repository from scratch.
        {
            "name": "git",
            "transport": "stdio",
            "command": ["uvx", "mcp-server-git"],
            "description": "Official Anthropic git server.",
        },
    ]

    # ---- Requirement #5/#6: our custom pharmacy MCP server -----------------
    if use_remote_pharmacy:
        servers.append(
            {
                "name": "pharmacy",
                "transport": "http",
                "url": PHARMACY_REMOTE_URL,
                "headers": {"X-API-Key": PHARMACY_API_KEY},
                "description": "Custom pharmacy chain server (REMOTE / cloud).",
            }
        )
    else:
        servers.append(
            {
                "name": "pharmacy",
                "transport": "stdio",
                "command": [python, str(SRC_ROOT / "servers" / "pharmacy" / "server_stdio.py")],
                "description": "Custom pharmacy chain server (LOCAL / stdio).",
            }
        )

    return servers
