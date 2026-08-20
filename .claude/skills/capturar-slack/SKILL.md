---
name: capturar-slack
description: Captura conversaciones relevantes de Slack (DMs, menciones, hilos activos) al second brain (raw/slack/). Usar para ingestar lo hablado en Slack del día, o dentro del pipeline diario. Tier 2 — best-effort; degrada con gracia si el MCP de Slack no está disponible.
---

# capturar-slack — ingesta de Slack

Captura lo relevante de Slack hacia `raw/slack/<FECHA>.md`. **Tier 2 / best-effort**: usa el MCP de
Slack. Si el MCP no está disponible (p.ej. corrida headless), informá y terminá sin error.

**Atribución por fecha del evento, NO por fecha de la corrida.** Cada mensaje se archiva en la fecha
*local* (tu timezone, default `America/Buenos_Aires` UTC-3) de su `ts`, no en el día en que corrió la
captura. Una corrida matinal con ventana de 24h trae mensajes de **ayer** — esos van al archivo de
**ayer**, no al de hoy.

## Pasos

0. **Cargá los tools del MCP (crítico en headless).** Los tools del MCP de Slack (p.ej.
   `mcp__claude_ai_Slack__*`, según cómo se llame tu conector) vienen **diferidos**: en una corrida
   `claude -p` no aparecen en la lista inmediata y hay que cargarlos con **ToolSearch usando `select:`
   y el nombre exacto** antes de usarlos. Corré:
   `ToolSearch` query `select:<slack_search_public_and_private>,<slack_read_channel>,<slack_read_thread>,<slack_search_channels>`
   (reemplazá `<...>` por los nombres completos del tool en tu entorno).

   **Cómo decidir disponibilidad (no lo decidas a ojo).** El health del conector es un dato del shell:
   ```bash
   python3 .claude/scripts/pipeline_preflight.py   # → checks.mcp.servers.slack.connected
   ```
   | Preflight | ToolSearch | Qué es | Qué hacés |
   |---|---|---|---|
   | `connected: true` | trae el schema | todo bien | capturá |
   | `connected: true` | **no** lo trae | el conector está sano pero **no quedó enumerado en esta sesión** (pasa en una fracción de las corridas headless: se caen juntos varios conectores de la misma plataforma mientras otros MCP siguen andando) | `deferred` — el wrapper relanza una sesión nueva, que suele resolverlo. **Nunca `skipped`** |
   | `connected: false` | — | falta auth (OAuth necesita browser, no se arregla headless) | `skipped` con el motivo |
   | `connected: true` | trae el schema, pero la llamada falla con socket error | proxy caído a mitad | reintentá (política de retry del pipeline) y si no → `deferred` |

   Nunca declares "Slack no disponible" sin haber mirado el preflight: el MCP suele conectar bien en la
   inmensa mayoría de las sesiones, así que un skip a ciegas descarta el día por nada.

1. Ventana por defecto: últimas 24h (ajustable; ampliala tras un gap). La captura puede abarcar
   **dos fechas** (ayer + hoy) → vas a escribir en uno o dos archivos según el `ts` de cada mensaje.
2. Resolvé tu `user_id` una vez (con `slack_search_users` por tu email, ej.
   `tu-usuario@ejemplo.com`) y guardalo para no gastar una llamada por corrida.
3. En paralelo, traé:
   - **DMs y group DMs** de la ventana dirigidos a vos.
   - **Menciones directas** (`<@USER_ID>` en la query de búsqueda), excluyendo tus propios mensajes
     y bots.
   - **Hilos activos** donde participaste y el último mensaje no es tuyo.
   - Canales de interés recurrentes (ej. `#tu-canal`) si hay novedad relevante.

   **Argumentos que hay que pasar bien** (errores comunes de invocación, no del MCP):
   - Leer un hilo requiere **`channel_id` + `message_ts`**, y el `message_ts` es el del **mensaje
     padre**, no el del reply que encontraste. El resultado de búsqueda trae `Channel: … (ID: C…)`,
     `Message_ts:` (el del reply) y un `Permalink` con `?thread_ts=<PADRE>&cid=<CANAL>`: **el padre
     es el `thread_ts` del permalink**. Si no lo tenés, no llames al tool.
   - Leer un canal toma un **ID** (`C…`, o un `user_id` para DMs), **no** el nombre del canal.
     Resolvé el nombre primero (búsqueda de canales); si ves `channel_not_found`, es que pasaste un
     nombre en vez de un ID.
4. **Bucketeá por fecha local del `ts`** (epoch → tu timezone → `YYYY-MM-DD`). Para cada fecha
   presente, escribí/actualizá `raw/slack/<fecha>.md`:
   ```markdown
   > **Fuente**: Slack · **Capturado**: <hoy> · ventana: últimas 24h

   # Slack — <fecha>

   ## <#canal o DM con Persona>
   - **<persona>** (<ts legible>): <mensaje resumido o textual> (ts: <ts>)
     - <respuesta / contexto del hilo>
   ```
   - Un hilo que cruza la medianoche se parte: cada mensaje bajo la fecha de su `ts`. Si un hilo
     quedó casi todo en una fecha, está bien dejar el contexto junto y notar la fecha del cruce.
   - Es captura cruda (bronze): preservá quién dijo qué y el `ts` para citar. No interpretes.
   - **Convención de headers de atribución** (crítico para `/compactar`): usá siempre el formato
     exacto `## DM con <Nombre Completo>` para DMs directos y `## Group DM con <P1> e <P2>` para
     grupos. `/compactar` lee estos headers para atribuir intercambios a personas conocidas de
     `wiki/personas/` (por nombre/alias) y promoverlos a su sección `## Interacciones`. Si el
     header no respeta el formato, la atribución falla silenciosamente.
5. **Privacidad**: no traigas canales sensibles que no aporten; nunca copies secretos/tokens que
   aparezcan en mensajes — referenciá que existen, no el valor.
6. **Idempotencia / merge**: archivo por fecha de evento. Si `raw/slack/<fecha>.md` ya existe,
   **mergeá** (agregá solo mensajes/hilos nuevos por `ts`, preservá lo ya escrito); no pises el día.
7. Si el MCP de Slack no responde, no escribas nada y reportá el estado según la tabla del paso 0:
   `deferred` (conector sano, sesión sin enumerar / proxy caído → se reintenta) o `skipped` (falta auth).
   Decí cuál de los dos es y con qué evidencia (`checks.mcp.servers.slack` + qué devolvió el ToolSearch).
