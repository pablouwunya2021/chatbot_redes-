# Wireshark Analysis — Client ↔ Remote MCP Server (Requirements #7 & #9)

This document explains **how to capture** the traffic between the chatbot
(host/client) and the **remote** pharmacy MCP server, and **analyses** the
captured messages: which JSON-RPC messages are the synchronization
(handshake), which are requests/petitions and which are responses, and what
happens at the **link, network, transport and application** layers.

---

## 1. Why capture against a *local plain-HTTP* deployment

Google Cloud Run (and any HTTPS endpoint) encrypts the payload with TLS, so a
capture there shows only ciphertext. To read the actual JSON-RPC messages we
run the **exact same container** locally over plain HTTP and capture the
loopback interface. (The Cloud Run deployment is still the "remote server"
deliverable; this is only to make the bytes observable. To capture the real
HTTPS traffic instead, set `SSLKEYLOGFILE` before launching the client and load
that key log into Wireshark — see §6.)

```bash
# Terminal 1 — the remote server over plain HTTP
docker build -f deploy/Dockerfile -t pharmacy-mcp .
docker run --rm -p 8000:8080 -e PHARMACY_API_KEY=demo-key pharmacy-mcp
# (or without Docker:)   PORT=8000 python src/servers/pharmacy/server_http.py
```

## 2. Start the capture

**Wireshark (GUI):** choose interface **Loopback: lo0** (macOS) / **Loopback
Adapter** (Windows) / **lo** (Linux), and set the capture/display filter:

```
tcp.port == 8000
```

**tshark (CLI equivalent):**

```bash
# macOS loopback = lo0, Linux = lo
sudo tshark -i lo0 -f "tcp port 8000" -w docs/wireshark/mcp_capture.pcapng
```

## 3. Generate the traffic

```bash
# Terminal 2
python src/demo_remote_session.py
```

This performs a full session (the same messages the chatbot sends). Stop the
capture afterwards. The session produces exactly the transcript in
`logs/remote_session.jsonl`.

---

## 4. The message sequence (what you will see)

The session is **13 JSON-RPC messages** = 6 request/response pairs + 1
notification. Over HTTP each one is an independent `POST /mcp` (requests and
notifications) and its HTTP reply (responses).

| # | JSON-RPC `method` / `id` | JSON-RPC classification | MCP role |
|---|--------------------------|-------------------------|----------|
| 1 | `initialize` (id 1) — **request** | petition / request | **synchronization** (handshake start) |
| 2 | result (id 1) — **response** | response | **synchronization** (capabilities & version negotiated) |
| 3 | `notifications/initialized` — **notification** | notification (no id, no reply) | **synchronization** (handshake complete) |
| 4 | `tools/list` (id 2) — **request** | petition / request | discovery |
| 5 | result (id 2) — **response** | response | tool catalogue returned |
| 6 | `tools/call` search_medications (id 3) — **request** | petition / request | invocation |
| 7 | result (id 3) — **response** | response | search results |
| 8 | `tools/call` recommend_for_symptoms (id 4) — **request** | petition / request | invocation |
| 9 | result (id 4) — **response** | response | recommendation |
| 10 | `tools/call` check_inventory (id 5) — **request** | petition / request | invocation |
| 11 | result (id 5) — **response** | response | stock |
| 12 | `tools/call` place_order (id 6) — **request** | petition / request | invocation |
| 13 | result (id 6) — **response** | response | order confirmation |

**How to tell them apart in Wireshark:**

- **Synchronization messages** — the first three: `initialize` (req), its
  result, and the `notifications/initialized` notification. They set up the
  session (protocol version + capabilities) before any real work.
- **Requests / petitions** — any packet whose JSON body has **both** a
  `"method"` **and** an `"id"` (`initialize`, `tools/list`, `tools/call`). In
  HTTP these are the `POST /mcp` packets.
- **Notifications** — a `"method"` but **no `"id"`**
  (`notifications/initialized`). No response is expected; the server answers at
  the HTTP layer with `202 Accepted` and an empty body.
- **Responses** — packets with an **`"id"` and a `"result"`** (or `"error"`),
  and **no `"method"`**. The `id` matches the request it answers. In HTTP these
  are the `200 OK` replies.

Useful Wireshark display filters:

```
http.request.method == "POST"          # every request/notification (POST /mcp)
http.response.code == 200              # every JSON-RPC response
http.response.code == 202              # the notification's ack (no JSON body)
json.key == "method"                   # requests + notifications
json.key == "result"                   # responses
frame contains "initialize"            # the handshake
frame contains "place_order"           # the order invocation
```

Real bytes of the first request (application-layer payload of packet #1):

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"clientInfo":{"name":"uvg-redes-chatbot","version":"1.0.0"}}}
```

and its response:

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"pharmacy-mcp","version":"1.0.0"},"instructions":"..."}}
```

---

## 5. Layer-by-layer analysis (Requirement #9)

For each `POST /mcp` you can expand the packet in Wireshark and see the classic
stack. Below is what happens at each layer for this project.

### Application layer — HTTP + JSON-RPC 2.0 / MCP
- The **payload** is a single JSON-RPC 2.0 message (the MCP protocol).
- It is carried by **HTTP/1.1**: requests are `POST /mcp` with
  `Content-Type: application/json` and headers `MCP-Protocol-Version`,
  `Mcp-Session-Id`, `X-API-Key`; responses are `200 OK` (JSON body) or
  `202 Accepted` (notifications, empty body).
- This is where the **synchronization vs request vs response** distinction
  lives (the JSON fields `method` / `id` / `result`), as classified in §4.
- MCP is an application-layer protocol, exactly like the OSI/TCP-IP model
  places it; JSON-RPC is "RPC over a message body", not a separate transport.

### Transport layer — TCP (port 8000)
- HTTP runs over **TCP**. You will see the **3-way handshake** `SYN`,
  `SYN, ACK`, `ACK` opening the connection before packet #1.
- TCP provides **reliable, ordered** delivery: each JSON message is segmented,
  sequence/ACK numbers track bytes, and the receiver acknowledges them. Large
  responses (e.g. `tools/list`, which is several KB) may span multiple TCP
  segments that Wireshark reassembles ("TCP segment of a reassembled PDU").
- The destination port **8000** identifies the server process; the client uses
  an ephemeral source port. Connections may be kept alive and reused across
  several JSON-RPC messages, or closed with `FIN`/`ACK` at the end.

### Network layer — IP
- Packets are routed with **IP**. In the loopback capture the addresses are
  `127.0.0.1 → 127.0.0.1`; against Cloud Run they would be your host's IP and
  the service's public IP. TTL, IP identification and fragmentation live here.
- IP is **best-effort and connectionless** — reliability is TCP's job, not IP's.

### Link layer — Loopback / Ethernet
- On loopback the frames use the **Null/Loopback** link type (macOS/BSD) or the
  Linux cooked/`lo` encapsulation — there is no real Ethernet MAC because the
  packets never leave the host.
- Over a real network this layer would be **Ethernet/Wi-Fi** with source and
  destination **MAC addresses**, resolved via ARP, and an MTU (~1500 bytes)
  that forces TCP to segment the larger JSON responses.

### Summary diagram

```
+-----------------------------------------------------------+
| Application | JSON-RPC 2.0 / MCP  (initialize, tools/call) |
|             | carried by HTTP/1.1 (POST /mcp, 200/202)     |
+-----------------------------------------------------------+
| Transport   | TCP  (port 8000, 3-way handshake, ACKs)      |
+-----------------------------------------------------------+
| Network     | IP   (127.0.0.1 ↔ 127.0.0.1 / public IPs)    |
+-----------------------------------------------------------+
| Link        | Loopback (or Ethernet + ARP + MAC on a LAN)  |
+-----------------------------------------------------------+
```

---

## 6. Optional: capturing the real HTTPS (Cloud Run) traffic

If you want to capture against the deployed HTTPS endpoint and still read the
payload, export a TLS key log so Wireshark can decrypt it:

```bash
export SSLKEYLOGFILE=$PWD/docs/wireshark/keylog.txt
python src/host/cli.py --remote      # Python's ssl writes session keys here
```
Then in Wireshark: *Preferences → Protocols → TLS → (Pre)-Master-Secret log
filename* → select `keylog.txt`, and filter on `tls` / `http2`. Without the key
log, TLS packets show only the encrypted `Application Data`, confirming that the
transport is protected but hiding the JSON-RPC content.

---

## 7. What to include in the report

- A screenshot of the loopback capture filtered by `tcp.port == 8000`.
- One expanded `POST /mcp` packet showing the HTTP headers and JSON body.
- The TCP 3-way handshake at the start of the connection.
- The table from §4 identifying synchronization / request / response messages.
- The layer-by-layer explanation from §5.
