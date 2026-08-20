---
name: refresh
description: Mini-pipeline intradía — re-captura Granola/Claude/Slack/GitHub, regenera la bitácora del día, genera TODOs, re-corre compactar diario y hace backup. Corre cada hora de 09:00 a 18:00 L-V vía launchd y además tras cada meeting (trigger event-driven post-meeting). Más liviano que el pipeline completo; sin Calendar. Usar también manualmente cuando querés que la bitácora y los TODOs del día reflejen reuniones que ya ocurrieron.
---

# refresh — mini-pipeline intradía

Versión liviana del pipeline diario. Corre varias veces por día sin conflicto porque cada paso es
idempotente. El pipeline completo (`/pipeline-diario`) sigue siendo el responsable del start-of-day
(suma Calendar). Además del schedule (cada hora 09:00–18:00 L-V), un trigger event-driven — el poller
`com.secondbrain.postmeeting`, disparado por el watcher `com.secondbrain.granola-transcript` cuando
marca un meeting como asentado — corre `/refresh` poco después de que termina cada meeting, así los
TODOs y la bitácora reflejan lo recién hablado sin esperar al próximo slot.

## Preflight + checkpoint (paso 0 — antes de capturar)

1. **Preflight de entorno** (determinístico, shell):
   ```bash
   python3 .claude/scripts/pipeline_preflight.py
   ```
   Parseá el JSON. `recommend_skip` son los tiers que el entorno ya descarta (`gh` no autenticado o
   ausente del PATH, sin red, **conector MCP sin auth**). Esos tiers se saltean: marcalos `skipped`
   con el motivo y no los corras. **No intentes `gh auth login` headless** (cuelga esperando el
   browser); en sesión interactiva, avisá al usuario que lo corra.

2. **Sondeo de MCP.** El preflight ya trae el health de cada conector en `checks.mcp.servers`
   (`claude mcp list`: `✔ Connected` vs `! Needs authentication`) y lista en
   `mcp_healthy_defer_if_missing` los que están sanos. Vos sondeás lo otro: si quedaron **enumerados en
   esta sesión**.
   - **Cargá los tools primero (crítico en headless).** En `claude -p` los tools `mcp__*` vienen
     **diferidos**: no aparecen en la lista inmediata y hay que cargarlos con **ToolSearch usando
     `select:` y el nombre EXACTO** antes de poder llamarlos. Un keyword-search flojo o un "no los veo"
     da **falsos negativos**. Cargalos así:
     `ToolSearch` query `select:mcp__granola__get_account_info,mcp__claude_ai_Slack__slack_search_public_and_private,mcp__claude_ai_Atlassian__atlassianUserInfo`
   - **Recién con el schema cargado**, hacé **una** llamada barata de prueba (Granola →
     `get_account_info`; Atlassian → `atlassianUserInfo`; Slack → no hace falta probe aparte, la primera
     búsqueda de la captura ya lo es).
   - **Cómo clasificar el resultado** (regla determinística — no lo decidas a ojo):
     | Preflight | ToolSearch / llamada | Estado del tier |
     |---|---|---|
     | `connected: true` | anda | corré el tier |
     | `connected: true` | el `select:` NO trae el schema | **`deferred`** — el conector está sano pero no quedó enumerado en esta sesión; el wrapper relanza una sesión nueva y ahí suele andar |
     | `connected: true` | socket error / sin respuesta | reintentá (política de retry) y si no → **`deferred`** |
     | `connected: false` | — | `skipped` (falta OAuth; no se arregla headless) |
     Pasa seguido que los 3 conectores de claude.ai (Slack/Calendar/Atlassian) no se enumeren juntos
     mientras Granola sí: eso es enumeración fallida de la sesión, **no** "MCP no disponible". Un
     `skipped` ahí descarta el día para nada (el conector conecta bien en la gran mayoría de las sesiones).

3. **Iniciá el checkpoint** y fijate qué saltear por resume:
   ```bash
   python3 .claude/scripts/pipeline_checkpoint.py start refresh
   ```
   Si `resumed: true`, los tiers en `skip` ya se completaron en una corrida que se cortó hace poco
   (dentro de la ventana de resume) → **no los rehagas**; corré solo los de `pending`. Si `resumed:
   false`, arrancás de cero (lo normal en cada slot horario).

## Política de retry (aplicar en cada tier de red/MCP)

- **Comandos shell con red** (`git push`, extractores): envolvelos con
  `.claude/scripts/retry.sh --attempts 3 --base 2 --label "<qué> " -- <cmd...>`. Reintenta con
  backoff exponencial + jitter ante cualquier exit ≠ 0 (cubre 500s, socket errors y timeouts que el
  comando propaga como fallo).
- **Llamadas MCP** (las hace el agente, no el shell): ante **500 / socket error / stream idle
  timeout / "overloaded"**, reintentá hasta 3 veces con backoff `5s → 15s → 30s` (el backoff corto de
  1-2-4s no alcanzaba: cuando el proxy se cae, tarda más que eso en volver). Si tras los 3 sigue
  fallando y el preflight lo vio `connected` → marcá el tier **`deferred`** (no `skipped`) y seguí.
  **Ningún tier debe abortar el pipeline.**

## Pasos

Después de cada paso, registrá el resultado en el checkpoint (el pipeline `refresh` es el primer
argumento — cada pipeline tiene su propio archivo de checkpoint, así una corrida de `refresh` que se
solapa con `pipeline-diario` no le pisa el progreso):
`python3 .claude/scripts/pipeline_checkpoint.py mark refresh <tier> <done|regenerated|skipped|deferred|failed> "<detalle>"`.

`deferred` es el estado clave de los tiers de MCP: significa "la fuente está sana, esta sesión no pudo
usarla". No cuenta como resuelto, así que el wrapper de launchd reabre la corrida y la relanza en sesión
nueva (reintentando ese tier y los downstream). `skipped` es un descarte definitivo de la corrida.

1. **granola** — `/capturar-granola` trae los **resúmenes** de los meetings nuevos vía el MCP de Granola
   (`list_meetings this_week` → `get_meetings`) → `raw/granola/`. **Tier 2 / MCP**: sondealo en el paso 0;
   si no responde → saltear (aplicá la política de retry MCP). Idempotente por `meeting_id`; no pisa los
   transcripts viejos del cache. → `mark refresh granola regenerated "<N meetings nuevos>"` (o `done` si
   no hubo nuevos; `skipped` si el MCP no respondió).
2. **claude** — `/capturar-claude` re-extrae las sesiones de Claude Code de hoy (y ayer si aplica).
   Headless-safe. → `mark refresh claude regenerated|done "<N sesiones>"`.
3. **slack** — `/capturar-slack` captura DMs, menciones e hilos de la ventana del día (Tier 2 / MCP).
   Clasificá con la tabla del paso 0: conector sin auth → `skipped`; conector sano que esta sesión no
   pudo usar → `deferred`. → `mark refresh slack done|deferred|skipped "<motivo>"`.
4. **github** — `/capturar-github` PRs recientes → `raw/github/` (Tier 2). El extractor ya degrada
   solo si `gh` falla; si el preflight recomendó saltear github → no lo corras.
   → `mark refresh github done|skipped "<N PRs / motivo>"`.
5. **bitacora** — `/bitacora` regenera `bitacora/<HOY>.md` con todo el `raw/` acumulado hasta ahora.
   Solo regenera la de hoy (no la de ayer — eso lo hace el pipeline completo de mañana).
   → `mark refresh bitacora regenerated`.
6. **todos** — `/todos` materializa los accionables nuevos detectados en la bitácora y el `raw/` de
   hoy. Idempotente: dedupea contra los TODOs existentes y contra Jira. → `mark refresh todos done "<N nuevos>"`.
7. **compactar** — `/compactar diario`: actualiza `## Interacciones` con 1-1s del calendario de hoy y
   stagea candidatos nuevos en `candidatos-gold/`. El sync de Jira corre vía MCP de Atlassian
   best-effort (aplicá la política de retry MCP; si no está → `skipped` parcial, no abortes).
   → `mark refresh compactar done|skipped`.
8. **backup** — `/backup` (commit + push; el push va envuelto en `retry.sh` — ver la SKILL de
   backup). Si no hubo cambios, es no-op silencioso. **Tiene que completarse sí o sí.**
   → `mark refresh backup done`.

## Cierre

- **Resumen de qué se regeneró vs. se salteó** (a partir del checkpoint):
  ```bash
  python3 .claude/scripts/pipeline_checkpoint.py summary refresh
  ```
  Mostralo en el output. Sirve además de material para el mensaje de commit del backup.
- Cerrá la corrida: `python3 .claude/scripts/pipeline_checkpoint.py done refresh`. Si algún tier quedó
  `deferred`, decilo explícito en el resumen: el wrapper va a relanzar una sesión nueva para
  reintentarlo, así que no es una pérdida del día.

## Reglas headless

- Si un paso falla, marcalo en el checkpoint (`failed`/`skipped`), logueá y continuá. El backup tiene
  que completarse sí o sí.
- No pidas confirmación interactiva en ningún paso.
