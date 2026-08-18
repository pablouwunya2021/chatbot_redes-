# Guion de Presentación — Chatbot MCP (FarmaValle)

Duración objetivo: **8–10 min**. La rúbrica pide cubrir: **funcionalidades
implementadas**, **dificultades y cómo se resolvieron**, y **lecciones
aprendidas**. Este guion las cubre las tres, con demos en vivo.

> Antes de empezar: `source .venv/bin/activate`, tener `.env` con tu API key,
> y abrir dos terminales. Deja la web corriendo en el navegador por si acaso.

---

## 0. Apertura (30 s)

> "Buenas. Mi proyecto es un **chatbot que usa el Model Context Protocol** para
> darle herramientas a un LLM. Lo importante: **implementé MCP a mano sobre
> JSON-RPC 2.0**, sin ningún SDK de MCP ni FastMCP. El chatbot es el
> **anfitrión**, y conecta tres servidores: Filesystem y Git oficiales, y uno
> **propio** para una **cadena de farmacias**, que corre **local y en la nube**."

Muestra el diagrama de `REPORTE.md` §3 (anfitrión → clientes → servidores).

## 1. Arquitectura (1 min)

- **Anfitrión**: `chatbot.py` (coordina) + `llm.py` (habla con Claude).
- **Cliente MCP hecho a mano**: `mcp_client.py` — JSON-RPC 2.0, dos transportes
  (stdio y HTTP).
- **Servidor propio**: `servers/pharmacy/core.py` (mismo código para local y
  remoto).

> "La regla es: un anfitrión, varios clientes, un servidor por cliente."

## 2. Demo 1 — Chat + contexto + herramientas propias (2 min)

Terminal: `python src/host/cli.py`

1. **Conocimiento general (req #1):**
   > "¿Quién fue Alan Turing?"
2. **Contexto (req #2):**
   > "¿En qué fecha nació?" — *señala que entendió que sigue hablando de Turing.*
3. **Herramienta propia (req #5):**
   > "Tengo fiebre y dolor de cabeza, ¿qué puedo tomar?"
   Muestra el chip `→ tool pharmacy__recommend_for_symptoms`.
4. **Seguimiento con inventario:**
   > "¿Ese lo tienen en Zona 10?" → `pharmacy__check_inventory`.
5. **Pedido:**
   > "Resérvame 2 con envío a nombre de Ana." → `pharmacy__place_order`, sale un `ORD-XXXX`.
6. **Log (req #3):** escribe `/log 15` y muestra los mensajes JSON-RPC.

*(Alternativa visual: haz lo mismo en la **web** `python src/ui/web/app.py` y
señala el panel **MCP Activity Log** a la derecha, que muestra el handshake en
vivo.)*

## 3. Demo 2 — Servidores oficiales Filesystem + Git (1.5 min)

Terminal: `python src/demo_git_filesystem.py`

> "Aquí el anfitrión usa dos servidores **oficiales**. El escenario: crear un
> repositorio, escribir un README con el servidor **Filesystem**, y hacer
> `add`, `commit` y `log` con el servidor **Git**."

- Señala el `commit hash` y el `git_log` al final.
- **Menciona el hallazgo:** "La versión actual del servidor Git oficial ya no
  trae `git_init`, así que el repo se crea con `git init` y todo lo demás va por
  MCP. Fue una dificultad real que documenté."

## 4. Demo 3 — Servidor remoto (nube) + Wireshark (2.5 min)

**Remoto (req #6):**

```bash
# terminal A
PORT=8000 python src/servers/pharmacy/server_http.py
# terminal B
python src/host/cli.py --remote
```
> "Es **el mismo servidor**, pero ahora por **HTTP**. El chatbot lo usa igual:
> solo cambió el transporte, no el contenido de los mensajes."

Haz una consulta de farmacia para probar el remoto.

**Wireshark (req #7 y #9):**

- Muestra la captura en loopback filtrada por `tcp.port == 8000`.
- Señala: el **handshake TCP** (SYN/SYN-ACK/ACK), luego `POST /mcp`.
- Abre un paquete y muestra el **JSON-RPC** dentro del HTTP.
- Explica la clasificación:
  - `initialize` + su result + `notifications/initialized` = **sincronización**.
  - `method`+`id` = **petición**; `id`+`result` = **respuesta**;
    `method` sin `id` = **notificación** (`202` en HTTP).
- Capas: **Aplicación** (JSON-RPC/MCP sobre HTTP) → **Transporte** (TCP, puerto,
  ACKs, reensamblado) → **Red** (IP) → **Enlace** (loopback/Ethernet).

## 5. Dificultades y cómo se resolvieron (1 min)

1. **Handshake obligatorio:** sin `notifications/initialized`, `tools/list`
   fallaba → lo implementé tal cual el estándar.
2. **stdout vs JSON-RPC:** los `print` del servidor rompían el canal → mandé los
   logs a **stderr** y los drené en un hilo.
3. **Emparejar por `id`:** el cliente lee hasta encontrar el `id` esperado y
   loguea las notificaciones intermedias.
4. **`git_init` eliminado** del servidor oficial → ajusté el escenario.
5. **TLS oculta el payload** en Cloud Run → capturé en HTTP plano local (o
   `SSLKEYLOGFILE`) para leer los mensajes.

## 6. Lecciones aprendidas (45 s)

- MCP resuelve **interoperabilidad**: una herramienta, cualquier LLM.
- Un protocolo de **aplicación** es independiente del **transporte**: el mismo
  `core.py` sirvió en stdio y en HTTP.
- Wireshark hizo tangible la **pila**: un "recomiéndame algo para la fiebre"
  baja por JSON-RPC → HTTP → TCP → IP → enlace.
- Escribirlo **sin SDK** me hizo entender *por qué* el estándar toma cada
  decisión.

## 7. Cierre (15 s)

> "En resumen: chatbot anfitrión, MCP hecho a mano en JSON-RPC, tres servidores
> (dos oficiales y uno propio), local y en la nube, con su análisis de red en
> Wireshark y una UI de terminal y web. Gracias, ¿preguntas?"

---

### Checklist de respaldo (si algo falla en vivo)

- [ ] `.env` con `ANTHROPIC_API_KEY` válido.
- [ ] `pip install -r requirements.txt` hecho dentro del venv.
- [ ] `npx` y `uvx` disponibles (Filesystem y Git).
- [ ] Captura `.pcapng` **ya guardada** en `docs/wireshark/` como plan B.
- [ ] Screenshots de cada demo por si no hay internet.
- [ ] Log `logs/mcp_interactions.jsonl` ya poblado (corre una demo antes).
