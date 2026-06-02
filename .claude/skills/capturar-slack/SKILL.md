---
name: capturar-slack
description: Captura conversaciones relevantes de Slack (DMs, menciones, hilos activos) al second brain (raw/slack/). Usar para ingestar lo hablado en Slack del día, o dentro del pipeline diario. Tier 2 — best-effort; degrada con gracia si el MCP de Slack no está disponible.
---

# capturar-slack — ingesta de Slack

Captura lo relevante de Slack hacia `raw/slack/<FECHA>.md`. **Tier 2 / best-effort**: usa el MCP de
Slack (claude.ai). Si el MCP no está disponible (p.ej. corrida headless), informá y terminá sin error.

**Atribución por fecha del evento, NO por fecha de la corrida.** Cada mensaje se archiva en la fecha
*local* (TZ Argentina, UTC-3) de su `ts`, no en el día en que corrió la captura. Una corrida matinal
con ventana de 24h trae mensajes de **ayer** — esos van al archivo de **ayer**, no al de hoy.

## Pasos

1. Ventana por defecto: últimas 24h (ajustable; ampliala tras un gap). La captura puede abarcar
   **dos fechas** (ayer + hoy) → vas a escribir en uno o dos archivos según el `ts` de cada mensaje.
2. Resolvé tu user id una vez con `slack_search_users` (tu nombre o email
   `tu-usuario@ejemplo.com`). Guardá el `user_id`.
3. En paralelo, traé:
   - **DMs y group DMs** de la ventana dirigidos a vos.
   - **Menciones directas** (`<@USER_ID>` en la query de `slack_search_public_and_private`),
     excluyendo tus propios mensajes y bots.
   - **Hilos activos** donde participaste y el último mensaje no es tuyo (usá `slack_read_thread`
     si el contexto viene truncado).
   - Canales de interés recurrentes del usuario (ej. `#tu-canal`) si hay novedad relevante.
4. **Bucketeá por fecha local del `ts`** (epoch → AR/UTC-3 → `YYYY-MM-DD`). Para cada fecha presente,
   escribí/actualizá `raw/slack/<fecha>.md`:
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
5. **Privacidad**: no traigas canales sensibles que no aporten; nunca copies secretos/tokens que
   aparezcan en mensajes — referenciá que existen, no el valor.
6. **Idempotencia / merge**: archivo por fecha de evento. Si `raw/slack/<fecha>.md` ya existe,
   **mergeá** (agregá solo mensajes/hilos nuevos por `ts`, preservá lo ya escrito); no pises el día.
7. Si el MCP de Slack no responde, no escribas nada y avisá: "Slack no disponible en esta corrida".
