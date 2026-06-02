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
1. Llamá `mcp__claude_ai_Google_Calendar__authenticate` → devuelve una URL.
2. Pedile al usuario que la abra en el browser y autorice (sugerí el prefijo `!` para pegar la URL
   de callback si hace falta).
3. Llamá `complete_authentication` con la callback URL. A partir de ahí se habilitan las tools de
   lectura.

## Pasos
1. Fecha: `FECHA=$(date +%F)`. Ventana: 00:00–23:59 ART del día.
2. Listá los eventos del día. Excluí los `responseStatus = declined` y los `eventType = focusTime`.
3. Escribí `raw/calendar/<FECHA>.md`:
   ```markdown
   > **Fuente**: Google Calendar · **Capturado**: <FECHA>

   # Agenda — <FECHA>

   - **<HH:MM–HH:MM>** <título> — participantes: <lista>
     - <nota: doc linkeado / requiere prep / organizador>
   ```
4. **Cross-link con Granola**: si un evento matchea (por título/horario) un transcript en
   `raw/granola/` del mismo día, referencialo (`→ ver raw/granola/<archivo>.md`). Esto ayuda a la
   bitácora a unir "reunión agendada" ↔ "transcript".
5. Idempotencia: archivo por fecha.
6. Si el MCP de Calendar no está conectado y el usuario no quiere hacer el OAuth ahora, avisá
   "Calendar no disponible" y terminá sin error (el pipeline degrada con gracia).
