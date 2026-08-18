# Documento Técnico — Cómo funciona todo (explicado para entenderlo)

Este documento te explica el proyecto **de arriba hacia abajo**, para que
puedas entenderlo, modificarlo y defenderlo en la presentación. No asume que ya
sepas MCP: empieza por la idea y va bajando al código.

---

## 1. La idea en una frase

> Un **LLM** solo sabe generar texto. Un **chatbot/anfitrión** le da
> **herramientas** (leer archivos, hacer git, consultar una farmacia). El
> **protocolo MCP** es el "idioma" estándar (mensajes **JSON-RPC 2.0**) con el
> que el anfitrión y esas herramientas se hablan.

Nosotros escribimos ese "idioma" **a mano** (sin librería MCP), tanto del lado
del **cliente** (el que pide) como de nuestro **servidor** (el que ejecuta).

## 2. Los tres actores (vocabulario MCP)

- **Servidor**: expone herramientas y las ejecuta. Ej.: Filesystem, Git, y el
  nuestro (Pharmacy).
- **Cliente**: mantiene la conexión con **un** servidor y sabe cómo hablarle.
- **Anfitrión (host)**: la app de IA que coordina **varios** clientes + el LLM.
  En nuestro caso es el chatbot.

Regla mental: **1 anfitrión → varios clientes → 1 servidor cada cliente.**

## 3. Mapa de archivos (qué hace cada uno)

```
src/
  host/                         ← EL ANFITRIÓN (chatbot)
    config.py       Registro de qué servidores hay y cómo se conectan.
    logger.py       Guarda cada mensaje JSON-RPC (requisito #3).
    mcp_client.py   ★ El cliente MCP hecho a mano (JSON-RPC 2.0, stdio y HTTP).
    llm.py          Habla con Claude (API) y corre el bucle de "usar herramientas".
    chatbot.py      Junta todo: conecta servidores, agrega herramientas, contexto.
    cli.py          Interfaz de terminal (UI extra).
  servers/pharmacy/             ← NUESTRO SERVIDOR MCP
    data.py         Catálogo, inventario y sucursales (datos ficticios).
    core.py         ★ Herramientas + el "despachador" JSON-RPC (a mano).
    server_stdio.py Transporte LOCAL: lee stdin, escribe stdout.
    server_http.py  Transporte REMOTO: POST /mcp (FastAPI) para la nube.
  ui/web/           Interfaz web (UI extra): app.py + static/index.html.
  demo_git_filesystem.py   Demo del requisito #4 (Filesystem + Git).
  demo_remote_session.py   Demo del requisito #6/#7 (sesión remota HTTP).
```

El símbolo ★ marca los dos archivos donde vive "la magia" del protocolo.

## 4. JSON-RPC 2.0 en 30 segundos

Todo mensaje es un JSON con `"jsonrpc": "2.0"`. Hay **tres formas**:

| Forma | Tiene | Ejemplo |
|-------|-------|---------|
| **Petición** (request) | `id` + `method` (+`params`) | `{"jsonrpc":"2.0","id":2,"method":"tools/list"}` |
| **Respuesta** (response) | `id` + `result` **o** `error` | `{"jsonrpc":"2.0","id":2,"result":{...}}` |
| **Notificación** | `method` **sin** `id` | `{"jsonrpc":"2.0","method":"notifications/initialized"}` |

El `id` sirve para **emparejar** cada respuesta con su petición. Las
notificaciones **no** esperan respuesta. Esto es exactamente lo que verás en
Wireshark.

## 5. El ciclo de vida de MCP (el "handshake")

Siempre en este orden, antes de poder usar herramientas:

```
Cliente ── initialize (req) ─────────────► Servidor
Cliente ◄─ result: versión + capacidades ─ Servidor
Cliente ── notifications/initialized ─────► Servidor   (notificación, sin respuesta)
Cliente ── tools/list (req) ──────────────► Servidor
Cliente ◄─ result: lista de herramientas ── Servidor
... luego tools/call cuantas veces haga falta ...
```

Si te saltas `notifications/initialized`, varios servidores oficiales **no**
contestan `tools/list`. Por eso decimos que MCP es *stateful* (tiene estado de
sesión). En el código esto está en `MCPServerConnection.initialize()`.

## 6. ¿Cómo decide el LLM usar una herramienta? (el bucle tool-use)

Este es el corazón del requisito #1 y #2. En `llm.py`:

```
1. Mandamos a Claude: el mensaje del usuario + la LISTA de herramientas.
2. Claude responde una de dos cosas:
   a) texto normal            → lo mostramos y terminamos el turno.
   b) "quiero usar la tool X" → stop_reason == "tool_use".
3. Si (b): ejecutamos la herramienta llamando al servidor MCP correcto,
   y le devolvemos a Claude el RESULTADO como un mensaje tool_result.
4. Volvemos al paso 2 (Claude ya puede redactar la respuesta final con el dato).
```

El **contexto** (requisito #2) es simplemente la lista `messages` que **no
borramos** entre turnos: por eso "¿y en qué fecha nació?" entiende que hablamos
de Alan Turing. Cada turno agrega mensajes a esa lista.

### Enrutamiento de herramientas

Como hay 3 servidores, nombramos cada herramienta `servidor__herramienta`
(p. ej. `pharmacy__check_inventory`). Cuando Claude pide
`pharmacy__check_inventory`, el anfitrión parte el nombre, ubica el cliente
`pharmacy` y llama `tools/call` con `name = check_inventory`. Está en
`ChatSession._dispatch_tool`.

## 7. Los dos transportes (misma conversación, distinto "cable")

**Punto clave para la presentación:** el *contenido* de los mensajes es idéntico;
solo cambia **cómo viajan**.

- **stdio** (`StdioTransport`): el servidor es un **proceso hijo**. Le
  escribimos un JSON + `\n` en su *stdin* y leemos su respuesta (JSON + `\n`)
  de su *stdout*. Los logs del servidor van a *stderr* para no ensuciar el
  canal. Así hablan Filesystem, Git y el Pharmacy **local**.
- **HTTP** (`HttpTransport`): cada mensaje se manda con `POST /mcp`. La
  respuesta viene en el cuerpo HTTP. Así habla el Pharmacy **remoto** (nube).

Como el `core.py` del servidor es el mismo, **el chatbot usa el remoto igual que
el local** (requisito #6): solo cambiamos una línea de configuración.

## 8. Nuestro servidor Pharmacy (el caso de industria)

Simula una **cadena de farmacias**. Flujo típico:

```
usuario: "tengo fiebre y dolor de cabeza"
  → recommend_for_symptoms(["fever","headache"])  → recomienda acetaminofén/ibuprofeno
usuario: "¿hay en Zona 10?"
  → check_inventory("MED-001","S1")               → 120 unidades
usuario: "resérvame 2 con envío"
  → place_order(...)                              → ORD-XXXX, total con envío
```

Detalles de diseño que conviene mencionar:

- **Seguridad clínica**: síntomas graves (dolor de pecho, dificultad para
  respirar, etc.) **no** se auto-medican; se deriva a atención profesional. Toda
  respuesta clínica lleva un *disclaimer*. Solo se manejan productos de venta
  libre (OTC).
- **Validación**: `place_order` verifica stock y calcula el total (envío = Q15).
- **Errores**: los problemas de negocio (sin stock, id inválido) se devuelven
  como `isError: true` en el resultado, no como error de protocolo. Los errores
  de protocolo (método inexistente) sí usan códigos JSON-RPC (`-32601`, etc.).

## 9. El log de interacciones (requisito #3)

`logger.py` agrega **cada** mensaje (petición/respuesta/notificación) a
`logs/mcp_interactions.jsonl` (una línea JSON por mensaje). Se ve con:

- Terminal: comando `/log 20`.
- Web: panel **MCP Activity Log** (se actualiza en cada turno).
- `--echo-log`: imprime cada mensaje en vivo mientras ocurre.

Esto también sirve para **contrastar con Wireshark**: los mismos mensajes que
loguea el cliente son los que captura Wireshark en el cable.

## 10. Cómo correr y demostrar cada parte

```bash
# Requisito #4 (Filesystem + Git oficiales)
python src/demo_git_filesystem.py

# Requisitos #1,#2,#3,#5 (chat + pharmacy local + contexto + log)
python src/host/cli.py            # o la web: python src/ui/web/app.py

# Requisito #6 (remoto): levantar el server HTTP y usar --remote
PORT=8000 python src/servers/pharmacy/server_http.py &
python src/host/cli.py --remote

# Requisito #7 (Wireshark): ver docs/wireshark/WIRESHARK_ANALYSIS.md
python src/demo_remote_session.py
```

## 11. Preguntas típicas del catedrático (y respuestas cortas)

- **¿Por qué JSON-RPC?** Es simple, sin estado en el formato, y separa `method`/
  `params`/`result`; MCP lo adopta como capa de aplicación.
- **¿Dónde está el estándar implementado a mano?** `mcp_client.py` (cliente) y
  `core.py` (servidor). No usamos SDK de MCP ni FastMCP.
- **¿Cómo mantienes contexto?** Guardo toda la conversación en `messages` y la
  reenvío completa en cada llamada a la API.
- **¿Qué cambia entre local y remoto?** Solo el transporte (stdio vs HTTP); el
  contenido JSON-RPC y la lógica del servidor son idénticos.
- **¿Cómo distingues en Wireshark sincronización, petición y respuesta?** Por
  los campos JSON: `method`+`id` = petición; `method` sin `id` = notificación
  (sincronización final); `id`+`result` = respuesta; el handshake `initialize`
  es la sincronización inicial.
- **¿Por qué el servidor escribe logs a stderr?** Porque *stdout* es el canal
  JSON-RPC en stdio; mezclar texto lo corrompería.
```
