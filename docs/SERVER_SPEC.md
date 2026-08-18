# Pharmacy MCP Server — Specification

Custom MCP server for the **FarmaValle** pharmacy chain. Implements the Model
Context Protocol by hand over JSON-RPC 2.0. The same `core.py` logic is exposed
through two transports:

- **stdio** (`server_stdio.py`) — local child process; newline-delimited JSON.
- **HTTP** (`server_http.py`) — remote; one JSON-RPC message per `POST /mcp`.

- Protocol: **MCP `2025-06-18`** over **JSON-RPC 2.0**
- Server identity: `{"name": "pharmacy-mcp", "version": "1.0.0"}`
- Capabilities advertised: `{"tools": {"listChanged": false}}`

---

## 1. Transport & endpoints

### stdio
| Direction | Framing |
|-----------|---------|
| client → server | one JSON object + `\n` on **stdin** |
| server → client | one JSON object + `\n` on **stdout** (logs go to **stderr**) |

### HTTP
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/mcp` | JSON-RPC endpoint. Body = one JSON-RPC message; reply = one JSON-RPC message (`application/json`). Notifications → **202 No Content**. |
| `GET`  | `/healthz` | Liveness probe (`{"status":"ok"}`). |
| `GET`  | `/` | Service metadata. |

**HTTP headers**

| Header | Who | Meaning |
|--------|-----|---------|
| `Content-Type: application/json` | both | JSON body |
| `Accept: application/json, text/event-stream` | client | accepts JSON or SSE |
| `MCP-Protocol-Version: 2025-06-18` | client | negotiated version |
| `Mcp-Session-Id: <hex>` | server→client on `initialize`, client→server after | session correlation |
| `X-API-Key: <key>` | client | optional shared-secret auth (401 if wrong) |

---

## 2. JSON-RPC methods (protocol surface)

| Method | Kind | Result |
|--------|------|--------|
| `initialize` | request | `protocolVersion`, `capabilities`, `serverInfo`, `instructions` |
| `notifications/initialized` | notification | — (no reply) |
| `ping` | request | `{}` |
| `tools/list` | request | `{ "tools": [ ... ] }` |
| `tools/call` | request | `{ "content": [...], "structuredContent": {...}, "isError": bool }` |

**Error object** (JSON-RPC): `{ "code", "message", "data?" }`. Codes used:
`-32700` parse error, `-32600` invalid request, `-32601` method not found,
`-32603` internal error, `-32001` unauthorized (HTTP auth).

Tool-level failures (e.g. unknown id, out of stock) are **not** JSON-RPC
errors; they return a normal result with `"isError": true` and an explanatory
text block, per MCP convention.

---

## 3. Tools

All tool results are returned as an MCP tool result: a `content` array with a
`text` block containing pretty-printed JSON, plus a machine-readable
`structuredContent` mirror.

### `list_stores`
List all branches. **Params:** none.
→ `{ "stores": [ {id, name, city, hours} ] }`

### `search_medications`
Full-text search across name/brand/ingredient/category/symptom.
**Params:** `query` *(string, required)*.
→ `{ query, count, results: [ {id, name, brand, category, price} ] }`

### `get_medication_info`
Full detail for one product.
**Params:** `medication_id` *(string, required)* e.g. `"MED-002"`.
→ `{ medication: {…, active_ingredient, dosage, warnings, price}, disclaimer }`

### `recommend_for_symptoms`
Recommend OTC products from symptoms. Emergency ("red-flag") symptoms return an
`emergency: true` payload advising professional care instead of a product.
**Params:** `symptoms` *(string[], required)*, `age_group` *(enum
adult|child|senior, optional)*.
→ `{ emergency, recommendations: [ {medication_id, name, addresses[], dosage, warnings, price} ], note, disclaimer }`

### `check_inventory`
Stock per store.
**Params:** `medication_id` *(string, required)*, `store_id` *(string, optional)*.
→ `{ medication_id, availability: [ {store_id, store_name, units_in_stock, in_stock} ] }`

### `place_order`
Create an order; validates stock and computes the total (delivery adds GTQ 15).
**Params:** `customer_name` *(string, req)*, `store_id` *(string, req)*,
`fulfilment` *(enum pickup|delivery)*, `items` *(array of `{medication_id,
quantity}`, req)*.
→ `{ order_id, customer_name, store, fulfilment, items[], total_gtq, status, created_at }`
On any invalid item / insufficient stock → `isError: true` with the reason.

### `get_order_status`
**Params:** `order_id` *(string, required)*.
→ the stored order object, or `isError: true` if unknown.

---

## 4. Worked examples (real bytes)

`initialize` request / response:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"clientInfo":{"name":"uvg-redes-chatbot","version":"1.0.0"}}}
```
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"pharmacy-mcp","version":"1.0.0"},"instructions":"FarmaValle pharmacy tools: ..."}}
```

`tools/call` (place_order) request / response:

```json
{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"place_order","arguments":{"customer_name":"Ana Lopez","store_id":"S1","fulfilment":"delivery","items":[{"medication_id":"MED-001","quantity":2}]}}}
```
```json
{"jsonrpc":"2.0","id":6,"result":{"content":[{"type":"text","text":"{ \"order_id\": \"ORD-4322106C\", \"total_gtq\": 85.0, \"status\": \"confirmed\" ... }"}],"isError":false}}
```

---

## 5. Data model (demo dataset)

- **Stores:** `S1` Zona 10, `S2` Zona 15, `S3` Cayalá.
- **Catalogue:** 10 OTC products (`MED-001`…`MED-010`) with brand, active
  ingredient, category, price (GTQ), dosage, warnings and associated symptoms.
- **Inventory:** units per `(store_id, medication_id)`.
- **Orders:** created in memory at runtime (`ORD-XXXXXXXX`).

The dataset is fictional and for demonstration only; the server provides
**information about OTC products, not medical diagnosis** (a disclaimer is
attached to every clinical response, and red-flag symptoms are routed to
professional care).
