---
name: capturar-calendar
description: Captura los eventos del día desde Google Calendar al second brain (raw/calendar/) y los cross-linkea con los transcripts de Granola. Usar para ingestar la agenda del día o dentro del pipeline diario. Tier 2 — requiere OAuth de Google Calendar; degrada con gracia si no está conectado.
---

# capturar-calendar — ingesta de Google Calendar

Captura la agenda del día hacia `raw/calendar/<FECHA>.md`. **Tier 2**: requiere el MCP de Google
Calendar autenticado (OAuth). Si no lo está, guiá el setup o degradá con gracia.

## Setup (una vez)
Si las tools de lectura de Calendar no están disponibles (solo aparecen `authenticate`/
`complete_authentication`):
1. Llamá el tool `authenticate` del MCP de Google Calendar → devuelve una URL.
2. Pedile al usuario que la abra en el browser y autorice (sugerí el prefijo `!` para pegar la URL
   de callback si hace falta).
3. Llamá `complete_authentication` con la callback URL. A partir de ahí se habilitan las tools de
   lectura.

## Pasos
1. Fecha: `FECHA=$(date +%F)`. Ventana: 00:00–23:59 (tu timezone, default `America/Buenos_Aires`)
   del día.
2. Listá los eventos del día. Excluí los `responseStatus = declined` y los `eventType = focusTime`.
   Filtrá también participantes que sean salas/recursos (emails `*@resource.calendar.google.com`) —
   no cuentan como personas.

2b. **Detección de 1-1** (por evento): un evento es 1-1 si se cumplen AMBAS condiciones:
   - **(A o B):** el título matchea `/\b1\s?[:\-\/]\s?1\b|\bone[\s\-]?on[\s\-]?one\b|\b1on1\b/i`
     (cubre `1:1`, `1-1`, `1on1`, `one-on-one`) **O** quedan exactamente 2 participantes-persona
     tras filtrar declined/recursos.
   - **Cardinalidad:** exactamente 2 participantes-persona reales (uno sos vos). Si A matchea pero
     hay >2 personas → grupal, **no** 1-1.

   Identificación de la persona: el participante que no sos vos → resolver a `[[wikilink]]`
   buscando nombre y `aliases:` en `wiki/personas/`. Sin match → texto plano (nunca inventar
   wikilink). **Calendar es la fuente de verdad del tipo:1-1** (no Granola ni Slack).

3. Escribí `raw/calendar/<FECHA>.md`:
   ```markdown
   > **Fuente**: Google Calendar · **Capturado**: <FECHA>

   # Agenda — <FECHA>

   - **<HH:MM–HH:MM>** <título> — participantes: <lista>
     - <nota: doc linkeado / requiere prep / organizador>
   ```
   Para eventos detectados como 1-1, agregá el marcador inline idempotente al final del título,
   antes del `—`:
   ```markdown
   - **15:30–16:00** Vos / Ana (1:1) `[tipo:1-1 · persona:[[ana-perez]]]` — participantes: ...
   ```
   El marcador es grep-eable (`grep "tipo:1-1"`) y Obsidian linkea la persona desde el raw.
   Como el archivo se reescribe entero por fecha (idempotencia del paso 5), no hay riesgo de
   duplicar el marcador.

4. **Cross-link con el resumen del meeting**: si un evento matchea (por título/horario) un archivo en
   `raw/granola/` del mismo día, referencialo (`→ ver raw/granola/<archivo>.md`). Esto ayuda a la
   bitácora a unir "reunión agendada" ↔ "resumen". (Granola suele nombrar el meeting con el título
   del evento de calendar, así que el match suele ser directo por título.)
5. Idempotencia: archivo por fecha.
6. Si el MCP de Calendar no está disponible, terminá sin error (el pipeline degrada con gracia) pero
   distinguí el motivo con el preflight (`checks.mcp.servers.calendar`): `connected: false` → `skipped`
   (falta el OAuth, no se completa headless); conector sano que esta sesión no pudo usar (el `ToolSearch
   select:` no trae el schema, o socket error) → **`deferred`**, que el wrapper reintenta en sesión nueva.
   Varios conectores de la misma plataforma suelen caerse juntos: si otro MCP de la misma familia
   tampoco aparece pero el resto sí, es enumeración fallida de la sesión, no falta de auth.
