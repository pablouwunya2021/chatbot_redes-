#!/usr/bin/env python3
"""
Drive a full session against the REMOTE (HTTP) pharmacy server and print every
JSON-RPC message exchanged. This is the exact traffic you capture with
Wireshark for requirement #7 (run the server over plain HTTP first).

Usage:
    # terminal 1
    PORT=8000 python src/servers/pharmacy/server_http.py
    # terminal 2
    python src/demo_remote_session.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "host"))

import config  # noqa: E402
from logger import InteractionLogger  # noqa: E402
from mcp_client import HttpTransport, MCPServerConnection  # noqa: E402


def main() -> None:
    url = os.getenv("PHARMACY_REMOTE_URL", "http://127.0.0.1:8000/mcp")
    logger = InteractionLogger(config.LOG_DIR / "remote_session.jsonl", echo=True)
    logger.clear()

    transport = HttpTransport(url, headers={"X-API-Key": config.PHARMACY_API_KEY})
    conn = MCPServerConnection("pharmacy", transport, logger)

    print(f"\n# Connecting to remote server: {url}\n")
    conn.initialize()                 # initialize (req/res) + initialized (notification)
    conn.list_tools()                 # tools/list (req/res)

    # A representative business flow (req/res each):
    conn.call_tool("search_medications", {"query": "headache"})
    conn.call_tool("recommend_for_symptoms", {"symptoms": ["fever", "headache"]})
    conn.call_tool("check_inventory", {"medication_id": "MED-001", "store_id": "S1"})
    order = conn.call_tool("place_order", {
        "customer_name": "Ana Lopez", "store_id": "S1", "fulfilment": "delivery",
        "items": [{"medication_id": "MED-001", "quantity": 2}],
    })
    conn.close()

    order_id = json.loads(order["content"][0]["text"])["order_id"]
    print(f"\n# Session complete. Placed order {order_id}.")
    print(f"# Full transcript saved to {logger.path}")


if __name__ == "__main__":
    main()
