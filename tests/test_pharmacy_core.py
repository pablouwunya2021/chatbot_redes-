#!/usr/bin/env python3
"""
Lightweight smoke tests for the pharmacy server's hand-written JSON-RPC layer.

No test framework required:
    python tests/test_pharmacy_core.py

Exercises the protocol surface directly against core.handle_message(), so it
runs without spawning a process or opening a socket.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src", "servers", "pharmacy"))
import core  # noqa: E402

_passed = 0
_failed = 0


def check(name: str, condition: bool) -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}")


def call(name: str, arguments: dict) -> dict:
    """Invoke a tool through the JSON-RPC dispatcher and return its result."""
    resp = core.handle_message(
        {"jsonrpc": "2.0", "id": 99, "method": "tools/call",
         "params": {"name": name, "arguments": arguments}}
    )
    return resp["result"]


def payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def main() -> None:
    # --- lifecycle -------------------------------------------------------
    init = core.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    check("initialize returns serverInfo", init["result"]["serverInfo"]["name"] == "pharmacy-mcp")
    check("initialize echoes protocol version",
          init["result"]["protocolVersion"] == core.PROTOCOL_VERSION)

    note = core.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    check("notification gets no reply", note is None)

    # --- discovery -------------------------------------------------------
    tl = core.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tl["result"]["tools"]}
    check("tools/list exposes 7 tools", len(names) == 7)
    check("place_order is advertised", "place_order" in names)

    # --- protocol error --------------------------------------------------
    bad = core.handle_message({"jsonrpc": "2.0", "id": 3, "method": "does/not/exist"})
    check("unknown method -> -32601", bad["error"]["code"] == -32601)

    # --- tool behaviour --------------------------------------------------
    rec = payload(call("recommend_for_symptoms", {"symptoms": ["fever", "headache"]}))
    check("recommendation is not empty", len(rec["recommendations"]) > 0)
    check("recommendation carries disclaimer", "disclaimer" in rec)

    emerg = payload(call("recommend_for_symptoms", {"symptoms": ["chest pain"]}))
    check("red-flag symptom flagged as emergency", emerg["emergency"] is True)
    check("emergency yields no product", emerg["recommendations"] == [])

    inv = payload(call("check_inventory", {"medication_id": "MED-001", "store_id": "S1"}))
    check("inventory returns a store row", len(inv["availability"]) == 1)

    order = payload(call("place_order", {
        "customer_name": "Test", "store_id": "S1", "fulfilment": "pickup",
        "items": [{"medication_id": "MED-001", "quantity": 1}]}))
    check("order id issued", order["order_id"].startswith("ORD-"))

    status = payload(call("get_order_status", {"order_id": order["order_id"]}))
    check("order can be looked up", status["status"] == "confirmed")

    oos = call("place_order", {
        "customer_name": "Test", "store_id": "S2", "fulfilment": "pickup",
        "items": [{"medication_id": "MED-002", "quantity": 99}]})
    check("out-of-stock order -> isError", oos.get("isError") is True)

    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
