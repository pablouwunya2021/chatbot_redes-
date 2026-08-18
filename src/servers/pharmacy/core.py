"""
Pharmacy MCP server -- core logic (transport-independent).

This module contains:
  * the TOOL definitions (name + JSON-Schema of inputs) returned by tools/list
  * the implementation of each tool
  * handle_message(): a hand-written JSON-RPC 2.0 dispatcher that both the
    stdio server and the HTTP server reuse, so the two transports expose an
    identical protocol surface (requirement #6: "the chatbot uses the remote
    server exactly like the local one").

No MCP SDK is used. Every request/response is a plain dict following the
JSON-RPC 2.0 and MCP shapes.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

try:  # allow both "import data" (stdio, run as script) and package import
    from . import data as data_mod
except ImportError:  # pragma: no cover
    import data as data_mod

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "pharmacy-mcp", "version": "1.0.0"}

MEDICAL_DISCLAIMER = (
    "This is general information about over-the-counter products, not a medical "
    "diagnosis. For persistent, severe or worsening symptoms, or for children, "
    "pregnancy or chronic conditions, consult a licensed healthcare professional."
)

# In-memory order store (resets on restart; fine for a demo).
_ORDERS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Tool catalogue (advertised via tools/list)
# ---------------------------------------------------------------------------
TOOLS: list[dict] = [
    {
        "name": "list_stores",
        "description": "List all pharmacy branches of the chain with their hours.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "search_medications",
        "description": (
            "Search the OTC catalogue by free text (matches product name, brand, "
            "active ingredient, category or associated symptom)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text, e.g. 'headache' or 'ibuprofen'."}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_medication_info",
        "description": "Get full details (ingredient, dosage, warnings, price) for one medication id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "medication_id": {"type": "string", "description": "e.g. 'MED-002'."}
            },
            "required": ["medication_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "recommend_for_symptoms",
        "description": (
            "Given a list of symptoms, recommend suitable OTC products. Routes "
            "emergency ('red-flag') symptoms to professional care instead of "
            "recommending a product."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symptoms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "e.g. ['fever', 'headache'].",
                },
                "age_group": {
                    "type": "string",
                    "enum": ["adult", "child", "senior"],
                    "description": "Optional; defaults to adult.",
                },
            },
            "required": ["symptoms"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_inventory",
        "description": "Check stock (units) of a medication, optionally at one store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "medication_id": {"type": "string"},
                "store_id": {"type": "string", "description": "Optional; omit to check all stores."},
            },
            "required": ["medication_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "place_order",
        "description": "Create an order for one or more medications for pickup or delivery.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "store_id": {"type": "string"},
                "fulfilment": {"type": "string", "enum": ["pickup", "delivery"]},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "medication_id": {"type": "string"},
                            "quantity": {"type": "integer", "minimum": 1},
                        },
                        "required": ["medication_id", "quantity"],
                    },
                },
            },
            "required": ["customer_name", "store_id", "items"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_order_status",
        "description": "Look up the status and details of an existing order id.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def _find_med(med_id: str) -> Optional[dict]:
    return next((m for m in data_mod.MEDICATIONS if m["id"] == med_id), None)


def tool_list_stores(_: dict) -> dict:
    return {"stores": data_mod.STORES}


def tool_search_medications(args: dict) -> dict:
    q = str(args.get("query", "")).strip().lower()
    if not q:
        return {"query": q, "results": []}
    hits = []
    for m in data_mod.MEDICATIONS:
        haystack = " ".join(
            [m["name"], m["brand"], m["active_ingredient"], m["category"], " ".join(m["symptoms"])]
        ).lower()
        if q in haystack:
            hits.append({k: m[k] for k in ("id", "name", "brand", "category", "price")})
    return {"query": q, "count": len(hits), "results": hits}


def tool_get_medication_info(args: dict) -> dict:
    m = _find_med(str(args.get("medication_id", "")))
    if not m:
        raise ValueError(f"Unknown medication_id: {args.get('medication_id')!r}")
    return {"medication": m, "disclaimer": MEDICAL_DISCLAIMER}


def tool_recommend_for_symptoms(args: dict) -> dict:
    symptoms = [str(s).strip().lower() for s in args.get("symptoms", []) if str(s).strip()]
    age_group = args.get("age_group", "adult")

    # 1) Safety gate: emergency symptoms are never self-treated.
    flagged = [s for s in symptoms if s in data_mod.RED_FLAG_SYMPTOMS]
    if flagged:
        return {
            "emergency": True,
            "flagged_symptoms": flagged,
            "advice": (
                "These symptoms may indicate a medical emergency. Do not self-medicate. "
                "Seek immediate professional care or call local emergency services."
            ),
            "recommendations": [],
            "disclaimer": MEDICAL_DISCLAIMER,
        }

    # 2) Score catalogue products by how many symptoms they address.
    scored = []
    for m in data_mod.MEDICATIONS:
        matched = [s for s in symptoms if any(s in ms or ms in s for ms in m["symptoms"])]
        if matched:
            scored.append((len(matched), matched, m))
    scored.sort(key=lambda t: t[0], reverse=True)

    recommendations = [
        {
            "medication_id": m["id"],
            "name": m["name"],
            "brand": m["brand"],
            "addresses": matched,
            "dosage": m["dosage"],
            "warnings": m["warnings"],
            "price": m["price"],
        }
        for _, matched, m in scored[:4]
    ]
    note = None
    if age_group in ("child", "senior"):
        note = (
            f"Dosing shown is for adults. Confirm the correct dose for a {age_group} "
            "with a pharmacist before use."
        )
    return {
        "emergency": False,
        "symptoms": symptoms,
        "age_group": age_group,
        "recommendations": recommendations,
        "note": note,
        "disclaimer": MEDICAL_DISCLAIMER,
    }


def tool_check_inventory(args: dict) -> dict:
    med_id = str(args.get("medication_id", ""))
    if not _find_med(med_id):
        raise ValueError(f"Unknown medication_id: {med_id!r}")
    store_id = args.get("store_id")
    rows = []
    for store in data_mod.STORES:
        if store_id and store["id"] != store_id:
            continue
        units = data_mod.INVENTORY.get((store["id"], med_id), 0)
        rows.append(
            {"store_id": store["id"], "store_name": store["name"],
             "units_in_stock": units, "in_stock": units > 0}
        )
    if store_id and not rows:
        raise ValueError(f"Unknown store_id: {store_id!r}")
    return {"medication_id": med_id, "availability": rows}


def tool_place_order(args: dict) -> dict:
    customer = str(args.get("customer_name", "")).strip()
    store_id = str(args.get("store_id", ""))
    fulfilment = args.get("fulfilment", "pickup")
    items = args.get("items", [])

    if not customer:
        raise ValueError("customer_name is required.")
    store = next((s for s in data_mod.STORES if s["id"] == store_id), None)
    if not store:
        raise ValueError(f"Unknown store_id: {store_id!r}")
    if not items:
        raise ValueError("At least one item is required.")

    line_items, total, problems = [], 0.0, []
    for it in items:
        med = _find_med(str(it.get("medication_id", "")))
        qty = int(it.get("quantity", 0))
        if not med:
            problems.append(f"Unknown medication_id: {it.get('medication_id')!r}")
            continue
        if qty < 1:
            problems.append(f"Invalid quantity for {med['id']}.")
            continue
        stock = data_mod.INVENTORY.get((store_id, med["id"]), 0)
        if stock < qty:
            problems.append(
                f"Only {stock} units of {med['id']} at {store_id} (requested {qty})."
            )
            continue
        subtotal = round(med["price"] * qty, 2)
        total += subtotal
        line_items.append(
            {"medication_id": med["id"], "name": med["name"],
             "quantity": qty, "unit_price": med["price"], "subtotal": subtotal}
        )

    if problems:
        raise ValueError("Order rejected: " + " ".join(problems))

    if fulfilment == "delivery":
        total = round(total + 15.0, 2)  # flat delivery fee

    order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
    order = {
        "order_id": order_id,
        "customer_name": customer,
        "store": store,
        "fulfilment": fulfilment,
        "items": line_items,
        "total_gtq": round(total, 2),
        "status": "confirmed",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _ORDERS[order_id] = order
    return order


def tool_get_order_status(args: dict) -> dict:
    order_id = str(args.get("order_id", ""))
    order = _ORDERS.get(order_id)
    if not order:
        raise ValueError(f"Unknown order_id: {order_id!r}")
    return order


TOOL_IMPL = {
    "list_stores": tool_list_stores,
    "search_medications": tool_search_medications,
    "get_medication_info": tool_get_medication_info,
    "recommend_for_symptoms": tool_recommend_for_symptoms,
    "check_inventory": tool_check_inventory,
    "place_order": tool_place_order,
    "get_order_status": tool_get_order_status,
}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 dispatch (shared by both transports)
# ---------------------------------------------------------------------------
def _result(mid: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid: Any, code: int, message: str, data: Any = None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": mid, "error": err}


def _call_tool(params: dict) -> dict:
    """Execute tools/call and wrap in the MCP tool-result shape."""
    name = params.get("name")
    arguments = params.get("arguments") or {}
    impl = TOOL_IMPL.get(name)
    if impl is None:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }
    try:
        payload = impl(arguments)
    except ValueError as exc:
        # Tool-level error: report via isError (MCP convention), not JSON-RPC error.
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": False,
    }


def handle_message(msg: dict) -> Optional[dict]:
    """Process a single JSON-RPC message.

    Returns a response dict, or None for notifications (which get no reply).
    """
    if msg.get("jsonrpc") != "2.0":
        return _error(msg.get("id"), -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}
    is_notification = "id" not in msg

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "FarmaValle pharmacy tools: search products, get info, get OTC "
                    "recommendations from symptoms, check inventory and place orders."
                ),
            }
        elif method in ("notifications/initialized", "notifications/cancelled"):
            return None  # notification: no response
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = _call_tool(params)
        else:
            if is_notification:
                return None
            return _error(mid, -32601, f"Method not found: {method}")
    except Exception as exc:  # pragma: no cover - safety net
        if is_notification:
            return None
        return _error(mid, -32603, f"Internal error: {exc}")

    if is_notification:
        return None
    return _result(mid, result)
