---
name: capturar-claude
description: Captura las sesiones recientes de Claude Code (transcripts JSONL locales) al second brain. Usar para ingestar qué se trabajó en Claude Code hacia raw/claude/, o cuando se corre el pipeline diario. Escribe un digest crudo agrupado por proyecto; NO sintetiza la bitácora (eso lo hace /bitacora).
---

# capturar-claude — ingesta de sesiones de Claude Code

Captura el trabajo hecho en Claude Code (transcripts en `~/.claude/projects/*/*.jsonl`) hacia
`raw/claude/YYYY-MM-DD.md`. Es **Tier 1 / headless-safe**: solo lee el filesystem, no usa MCP.

**Atribución por fecha del evento, NO por fecha de la corrida.** Cada sesión se archiva en la fecha
*local* (tu timezone, default `America/Buenos_Aires` UTC-3) en que ocurrió. Una sesión que abarca
varios días aporta a cada fecha que tocó ("dividir por día"). Esto evita el sesgo de que el laburo de
anoche caiga en el archivo de hoy: una corrida matinal barre la tarde/noche anterior, y esa actividad
va a **su** día.

## Pasos

1. Corré el extractor (default: `auto` = watermark auto-sanable — barre desde la última captura en
   `raw/claude/` hasta hoy, así un lunes absorbe el finde y una vuelta de vacaciones el gap entero sin
   tocar nada; clamp a 14 días). Pasá un N explícito para forzar una ventana puntual:
   ```bash
   python3 .claude/scripts/extract_claude_sessions.py "${1:-auto}"
   ```
   El extractor ya bucketea por fecha local con cutoff alineado a medianoche.
2. Parseá el JSON. Estructura: `cutoff_date`, `dates` (lista de fechas con actividad), y
   `by_date[<fecha>]` = `{jira_keys, entries}`. Cada `entry`: `project`, `title`, `branch`,
   `jira_keys`, `keywords`, `message_count`, `first_ts`, `last_ts`. Las entries se bucketean por
   `(fecha, branch)`: una sesión multi-tema produce **una entry por branch** (la key de Jira sale del
   branch, señal primaria). Al renderizar, **fusioná entries del mismo proyecto + key** en un bullet.
3. **Por cada fecha en `dates`**, escribí/actualizá `raw/claude/<fecha>.md` (NO un solo archivo "hoy"):
   ```markdown
   > **Fuente**: sesiones de Claude Code · **Capturado**: <hoy> · ventana: <N> día(s)

   # Sesiones de Claude Code — <fecha>

   ## <proyecto>
   - <título resumido de la sesión> (<PROJ-KEY> si hay) — branch `<branch>`
     - <keyword/contexto relevante si aporta>
   ```
   Reglas:
   - Agrupá por `project`. Mapeá `home` / paths sueltos a "general" si conviene; fusioná entries
     del mismo proyecto+tema en un bullet.
   - Mantené las keys de Jira entre paréntesis. **Descartá falsos positivos del regex** (p.ej.
     `AES-256`, `UTF-8`): solo keys de tu prefijo de proyecto real (ej. `PROJ-NNN`).
   - Es captura cruda: NO la escribas en pasado ni la edites como bitácora; es el insumo para `/bitacora`.
   - Filtrá ruido obvio (sesiones sin título útil, `/exit`, `/mcp`, evals).
4. **Idempotencia / merge** (clave para no perder ni pisar):
   - Si `raw/claude/<fecha>.md` **no existe** → crealo desde el bucket.
   - Si **ya existe** → **mergeá**: agregá solo los entries (sesiones/temas) que todavía no están
     representados; **preservá el texto curado existente**. NO regeneres desde cero un archivo de
     un día previo (perderías síntesis hecha a mano).
   - Excepción: el archivo de **hoy** se puede regenerar entero (es la captura viva, crece en el día).
5. Informá en una línea por fecha: cuántas sesiones/proyectos se capturaron o mergearon en cada `<fecha>`.
