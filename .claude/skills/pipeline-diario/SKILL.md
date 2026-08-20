---
name: pipeline-diario
description: Corre el pipeline diario completo del second brain de punta a punta. Lo dispara el cron (launchd) cada mañana, pero también se puede correr a mano. Captura todas las fuentes, arma la bitácora, genera TODOs y hace backup. Tier 1 garantizado + Tier 2 best-effort.
---

# pipeline-diario — orquestación diaria

Corre todo el flujo del día. Diseñado para correr **headless** (lanzado por launchd) pero también a mano.

## Preflight + checkpoint (paso 0 — antes de capturar)

1. **Preflight de entorno** (determinístico, shell):
   ```bash
   python3 .claude/scripts/pipeline_preflight.py
   ```
   Parseá el JSON. `recommend_skip` son los tiers que el entorno ya descarta (`gh` no autenticado o
   ausente del PATH, sin red, **conector MCP sin auth**). Esos tiers se saltean: marcalos `skipped`
   con el motivo. **No intentes `gh auth login` headless** (cuelga); en sesión interactiva, avisá.

2. **Sondeo de MCP.** El preflight ya trae el health de cada conector en `checks.mcp.servers`
   (`claude mcp list`: `✔ Connected` vs `! Needs authentication`) y lista los sanos en
   `mcp_healthy_defer_if_missing`. Vos sondeás lo otro: si quedaron **enumerados en esta sesión**.
   - **Cargá los tools primero (crítico en headless).** En una corrida `claude -p` los tools `mcp__*`
     vienen **diferidos**: no aparecen en la lista inmediata y hay que cargarlos con **ToolSearch usando
     `select:` y el nombre EXACTO** antes de poder llamarlos. Un keyword-search flojo o un "no los veo en
     la lista" da **falsos negativos**. Cargalos así:
     `ToolSearch` query `select:mcp__granola__get_account_info,mcp__claude_ai_Slack__slack_search_public_and_private,mcp__claude_ai_Google_Calendar__list_calendars,mcp__claude_ai_Atlassian__atlassianUserInfo`
   - **Recién con el schema cargado**, hacé **una** llamada barata de prueba por MCP (Granola →
     `get_account_info`; Calendar → `list_calendars`; Atlassian → `atlassianUserInfo`; Slack → la primera
     búsqueda de la captura ya es el probe).
   - **Cómo clasificar el resultado** (regla determinística — no lo decidas a ojo):
     | Preflight | ToolSearch / llamada | Estado del tier |
     |---|---|---|
     | `connected: true` | anda | corré el tier |
     | `connected: true` | el `select:` NO trae el schema | **`deferred`** — conector sano que no quedó enumerado en esta sesión; el wrapper relanza una sesión nueva |
     | `connected: true` | socket error / sin respuesta | reintentá (política de retry) y si no → **`deferred`** |
     | `connected: false` | — | `skipped` (falta OAuth, no se arregla headless; un intento de `authenticate` y si devuelve URL → `skipped`) |
     Pasa seguido que los 3 conectores de claude.ai (Slack/Calendar/Atlassian) no se enumeren juntos
     mientras Granola sí: eso es enumeración fallida de la sesión, **no** "MCP no disponible".

3. **Iniciá el checkpoint** y fijate qué saltear por resume:
   ```bash
   python3 .claude/scripts/pipeline_checkpoint.py start pipeline-diario
   ```
   Si `resumed: true`, los tiers en `skip` ya se completaron en una corrida que se cortó hace poco →
   **no los rehagas**; corré solo los `pending`.

## Política de retry (aplicar en cada tier de red/MCP)

- **Comandos shell con red** (`git push`, extractores): envolvelos con
  `.claude/scripts/retry.sh --attempts 3 --base 2 --label "<qué> " -- <cmd...>` (backoff exponencial
  + jitter ante exit ≠ 0; cubre 500s, socket errors y timeouts propagados como fallo).
- **Llamadas MCP**: ante **500 / socket error / stream idle timeout / "overloaded"**, reintentá hasta
  3 veces con backoff `5s → 15s → 30s` (el backoff de 1-2-4s no alcanzaba: cuando el proxy se cae tarda
  más que eso en volver); si tras los 3 sigue fallando y el preflight lo vio `connected` → **`deferred`**
  (no `skipped`) y seguí.

## Orden de ejecución

Después de cada tier, registrá el resultado (el pipeline `pipeline-diario` es el primer argumento —
cada pipeline tiene su propio archivo de checkpoint, así una corrida no le pisa el progreso a un
`refresh` que se solape en el tiempo):
`python3 .claude/scripts/pipeline_checkpoint.py mark pipeline-diario <tier> <done|regenerated|skipped|deferred|failed> "<detalle>"`.

`deferred` es el estado clave de los tiers de MCP: "la fuente está sana, esta sesión no pudo usarla". No
cuenta como resuelto → el wrapper de launchd reabre la corrida y la relanza en sesión nueva (reintenta ese
tier y los downstream). `skipped` es un descarte definitivo de la corrida.

### Tier 1 — siempre (headless-safe)
1. **claude** — `/capturar-claude` digest de sesiones → `raw/claude/`. → `mark pipeline-diario claude`.
2. **bitacora** — `/bitacora` sintetiza las fechas tocadas por las capturas → `bitacora/<FECHA>.md`.
   Una corrida matinal completa el `raw/` de **ayer** con el trabajo de anoche: regenerá la bitácora
   de **ayer y hoy**. → `mark pipeline-diario bitacora regenerated`.

### Tier 2 — best-effort (degrada con gracia; aplicá la política de retry MCP)
3. **granola** — `/capturar-granola` trae los **resúmenes** de los meetings vía el MCP de Granola
   (`list_meetings this_week` → `get_meetings`) → `raw/granola/`. Si el sondeo lo marcó caído → saltear.
   Idempotente por `meeting_id`; no pisa los transcripts viejos del cache. → `mark pipeline-diario granola done|skipped`.
4. **slack** — `/capturar-slack` DMs/menciones/hilos → `raw/slack/`. Clasificá con la tabla del paso 0:
   conector sin auth → `skipped`; conector sano que esta sesión no pudo usar → `deferred`.
   → `mark pipeline-diario slack done|deferred|skipped`.
5. **github** — `/capturar-github` PRs recientes → `raw/github/`. Si el preflight recomendó saltear →
   no lo corras. → `mark pipeline-diario github done|skipped "<N PRs / motivo>"`.
6. **calendar** — `/capturar-calendar` agenda del día → `raw/calendar/`. Sin OAuth → `skipped`.
   - Si corriste Tier 2 después de la bitácora, volvé a pasar `/bitacora` para incorporar
     Granola/Slack/GitHub/Calendar (re-`mark pipeline-diario bitacora regenerated`). → `mark pipeline-diario calendar done|skipped`.

### Cierre
7. **todos** — `/todos` materializa los pendientes detectados como notas. → `mark pipeline-diario todos done "<N>"`.
8. **compactar** — `/compactar diario` promueve a gold lo event-driven (Interacciones + Jira sync vía
   MCP de Atlassian) y stagea candidatos. **Best-effort**: aplicá retry MCP; si falla, `skipped` y
   seguí a backup. No debe abortar. → `mark pipeline-diario compactar done|skipped`.
9. **backup** — `/backup` commit + push (el push va envuelto en `retry.sh`). → `mark pipeline-diario backup done`.

- **Resumen de qué se regeneró vs. se salteó** (a partir del checkpoint):
  ```bash
  python3 .claude/scripts/pipeline_checkpoint.py summary pipeline-diario
  ```
  Mostralo; sirve además de material para el mensaje de commit del backup. Cerrá la corrida:
  `python3 .claude/scripts/pipeline_checkpoint.py done pipeline-diario`.

## Reglas para corrida headless
- Nunca pidas confirmación interactiva; si una fuente no está disponible, marcala `skipped` y seguí.
- Ningún paso de Tier 2 debe abortar el pipeline: Tier 1 + backup tienen que completarse sí o sí.
