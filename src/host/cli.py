#!/usr/bin/env python3
"""
Terminal chatbot (front-end #1, part of the 15% UI extra).

A Rich-based command-line interface over the ChatSession host. Besides normal
chat it exposes slash-commands to inspect the MCP layer, which double as the
"show the log" feature (requirement #3) and as a way to drive deterministic
tool calls for the Wireshark capture (requirement #7).

Usage:
    python src/host/cli.py                # local pharmacy server (stdio)
    python src/host/cli.py --remote       # remote pharmacy server (HTTP)
    python src/host/cli.py --echo-log     # print every JSON-RPC message live
"""
from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from chatbot import ChatSession

console = Console()

BANNER = """[bold green]FarmaValle Chatbot[/bold green]  ·  UVG Redes · MCP host
Type your message, or a command. [dim]/help[/dim] for commands, [dim]/quit[/dim] to exit."""

HELP = """
[bold]Commands[/bold]
  [cyan]/help[/cyan]                       show this help
  [cyan]/servers[/cyan]                    list connected MCP servers
  [cyan]/tools[/cyan]                      list every available tool
  [cyan]/log[/cyan] [dim][N][/dim]                   show last N MCP messages (default 20)
  [cyan]/call[/cyan] server tool {json}    call a tool directly (no LLM)
  [cyan]/reset[/cyan]                      clear the conversation context
  [cyan]/quit[/cyan]                       exit
"""


def on_event(kind: str, payload: dict) -> None:
    """Live feedback while the model works."""
    if kind == "tool_call":
        console.print(
            f"  [magenta]→ tool[/magenta] [bold]{payload['name']}[/bold] "
            f"[dim]{json.dumps(payload['input'], ensure_ascii=False)}[/dim]"
        )
    elif kind == "tool_result":
        tag = "[red]error[/red]" if payload["is_error"] else "[green]ok[/green]"
        preview = payload["text"].replace("\n", " ")[:100]
        console.print(f"  [magenta]← result[/magenta] {tag} [dim]{preview}[/dim]")


def cmd_servers(session: ChatSession) -> None:
    table = Table(title="Connected MCP servers")
    for col in ("name", "transport", "server", "tools"):
        table.add_column(col)
    for s in session.server_summary():
        info = s["server_info"]
        table.add_row(
            s["name"], s["transport"],
            f"{info.get('name','?')} {info.get('version','')}", str(s["tool_count"]),
        )
    console.print(table)


def cmd_tools(session: ChatSession) -> None:
    table = Table(title="Available tools")
    table.add_column("tool (namespaced)")
    table.add_column("description")
    for t in session.list_tools():
        table.add_row(t["name"], (t["description"] or "")[:70])
    console.print(table)


def cmd_log(session: ChatSession, n: int) -> None:
    entries = session.logger.read_entries()[-n:]
    table = Table(title=f"Last {len(entries)} MCP messages (log)")
    for col in ("seq", "server", "transport", "dir", "method / result"):
        table.add_column(col)
    for e in entries:
        msg = e["message"]
        label = msg.get("method") or (
            "result" if "result" in msg else "error" if "error" in msg else "-"
        )
        table.add_row(
            str(e["seq"]), e["server"], e["transport"], e["direction"], str(label)
        )
    console.print(table)


def cmd_call(session: ChatSession, rest: str) -> None:
    """/call <server> <tool> <json-args>"""
    try:
        server, tool, *json_parts = rest.split(" ", 2)
        args = json.loads(json_parts[0]) if json_parts else {}
    except (ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Usage: /call <server> <tool> {{json}}  ({exc})[/red]")
        return
    try:
        result = session.call_tool_direct(server, tool, args)
        console.print(Panel(json.dumps(result, ensure_ascii=False, indent=2),
                            title=f"{server}.{tool}", border_style="green"))
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")


def main() -> None:
    parser = argparse.ArgumentParser(description="FarmaValle MCP chatbot (terminal).")
    parser.add_argument("--remote", action="store_true",
                        help="use the remote (HTTP) pharmacy server instead of local stdio.")
    parser.add_argument("--echo-log", action="store_true",
                        help="print every JSON-RPC message as it happens.")
    args = parser.parse_args()

    console.print(Panel(BANNER, border_style="green"))
    session = ChatSession(use_remote_pharmacy=args.remote, echo_log=args.echo_log,
                          console=console)

    with console.status("[green]Connecting to MCP servers...[/green]"):
        status = session.connect_all()
    for name, st in status.items():
        color = "green" if st.startswith("ok") else "yellow" if st == "skipped" else "red"
        console.print(f"  [{color}]•[/{color}] {name}: {st}")

    if not session.enable_llm:
        console.print(
            "[yellow]No ANTHROPIC_API_KEY set: chat is disabled, but you can still "
            "use /tools, /servers, /log and /call to drive the MCP servers.[/yellow]"
        )

    try:
        while True:
            try:
                user = console.input("\n[bold cyan]you ›[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user:
                continue

            if user.startswith("/"):
                cmd, _, rest = user[1:].partition(" ")
                if cmd in ("quit", "exit", "q"):
                    break
                elif cmd == "help":
                    console.print(HELP)
                elif cmd == "servers":
                    cmd_servers(session)
                elif cmd == "tools":
                    cmd_tools(session)
                elif cmd == "log":
                    cmd_log(session, int(rest) if rest.strip().isdigit() else 20)
                elif cmd == "call":
                    cmd_call(session, rest)
                elif cmd == "reset":
                    session.reset_context()
                    console.print("[green]Context cleared.[/green]")
                else:
                    console.print(f"[red]Unknown command: /{cmd}[/red] ([dim]/help[/dim])")
                continue

            # Normal chat turn.
            try:
                answer = session.chat(user, on_event=on_event)
                console.print("\n[bold green]bot ›[/bold green]")
                console.print(Markdown(answer or "(no answer)"))
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/red]")
    finally:
        session.close_all()
        console.print("\n[dim]Session closed. Log saved to logs/mcp_interactions.jsonl[/dim]")


if __name__ == "__main__":
    main()
