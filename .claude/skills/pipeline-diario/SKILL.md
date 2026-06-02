---
name: pipeline-diario
description: Corre el pipeline diario completo del second brain de punta a punta. Lo dispara el cron (launchd) cada mañana, pero también se puede correr a mano. Captura todas las fuentes, arma la bitácora, genera TODOs y hace backup. Tier 1 garantizado + Tier 2 best-effort.
---

# pipeline-diario — orquestación diaria

Corre todo el flujo del día. Diseñado para correr **headless** (lanzado por launchd) pero también a mano.

## Orden de ejecución

### Tier 1 — siempre (headless-safe; garantiza no perder Granola)
1. `/capturar-claude` — digest de sesiones de Claude Code → `raw/claude/`.
2. `/capturar-granola` — transcripts nuevos de meetings → `raw/granola/`. **Crítico** (expiry 7 días).
   Extrae del cache local cifrado (sin MCP); además un LaunchAgent (`com.secondbrain.granola-transcript`) lo
   corre en cada escritura del cache, así que la captura ya es continua — este paso es el catch-all.
3. `/bitacora` — sintetiza las notas de las fechas tocadas por las capturas → `bitacora/<FECHA>.md`.
   Como las capturas atribuyen por fecha del evento, una corrida matinal completa el `raw/` de **ayer**
   con el trabajo de anoche: regenerá la bitácora de **ayer y hoy** (no solo la de hoy).

### Tier 2 — best-effort (degrada con gracia si el MCP de claude.ai no está disponible headless)
4. `/capturar-slack` — DMs/menciones/hilos → `raw/slack/`. Si Slack no responde, seguí.
5. `/capturar-calendar` — agenda del día → `raw/calendar/`. Si no hay OAuth, seguí.
   - Si corriste Tier 2 después de la bitácora, volvé a pasar `/bitacora` para incorporar Slack/Calendar.

### Cierre
6. `/todos` — materializa los pendientes detectados como notas en `todos/`.
7. `/backup` — commit + push del vault.

## Reglas para corrida headless
- Nunca pidas confirmación interactiva; si una fuente no está disponible, logueala y seguí.
- Ningún paso de Tier 2 debe abortar el pipeline: Tier 1 + backup tienen que completarse sí o sí.
- Al final, dejá un resumen de una línea de qué se capturó (sirve como mensaje de commit del backup).
