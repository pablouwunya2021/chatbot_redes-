"""
Interaction logger (project requirement #3).

Every JSON-RPC message exchanged with any MCP server is:
  1. appended to a JSON-Lines file (logs/mcp_interactions.jsonl), and
  2. optionally echoed to the console as a compact, human-readable line.

Keeping the raw messages lets us (a) show the log to the user on demand and
(b) cross-check against the Wireshark capture of the remote server.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class InteractionLogger:
    def __init__(self, path: Path, echo: bool = False, console: Optional[Any] = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.echo = echo
        self.console = console
        self._lock = threading.Lock()
        self._seq = 0

    def log(self, direction: str, server: str, transport: str, message: dict) -> dict:
        """Record one message.

        direction: "request" | "response" | "notification" | "error" | "info"
        server:    logical server name (e.g. "pharmacy")
        transport: "stdio" | "http"
        message:   the raw JSON-RPC object (or a small info dict)
        """
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "ts": datetime.now(timezone.utc).isoformat(),
                "server": server,
                "transport": transport,
                "direction": direction,
                "message": message,
            }
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if self.echo:
            self._echo(entry)
        return entry

    def _echo(self, entry: dict) -> None:
        msg = entry["message"]
        method = msg.get("method")
        mid = msg.get("id")
        label = method or ("result" if "result" in msg else "error" if "error" in msg else "?")
        arrow = {
            "request": "-->",
            "response": "<--",
            "notification": "-->",
            "error": "<--",
            "info": "  •",
        }.get(entry["direction"], "   ")
        line = f"[{entry['server']}/{entry['transport']}] {arrow} {label}" + (
            f" (id={mid})" if mid is not None else ""
        )
        if self.console is not None:
            color = {
                "request": "cyan",
                "notification": "magenta",
                "response": "green",
                "error": "red",
                "info": "yellow",
            }.get(entry["direction"], "white")
            self.console.print(f"[dim]{line}[/dim]", style=color)
        else:
            print(line)

    def read_entries(self) -> list[dict]:
        """Read back every logged entry (used by the `/log` command)."""
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out

    def clear(self) -> None:
        self.path.write_text("", encoding="utf-8")
        self._seq = 0
