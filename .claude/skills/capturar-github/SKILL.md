---
name: capturar-github
description: Captura PRs recientes de GitHub (vía `gh` CLI) al second brain (raw/github/). Usar para ingestar actividad de PRs de los repos de trabajo, o dentro del pipeline diario. Tier 2 best-effort — si `gh` no está autenticado o hay error de red, logueá y continuá sin abortar el pipeline.
---

# capturar-github — ingesta de PRs de GitHub

Captura los PRs con actividad reciente de los repos configurados en `.claude/config/github-repos.txt`
hacia `raw/github/YYYY-MM-DD.md`. Usa `gh pr list --json` (sin MCP); requiere `gh auth` y red.

**Atribución por fecha del evento, NO por fecha de la corrida.** Cada PR se archiva en la fecha
*local* (tu timezone, default `America/Buenos_Aires` UTC-3) de su `updatedAt`. Una corrida puede
escribir en **varios** archivos de fecha si hubo actividad en días distintos.

**Repos configurados**: `.claude/config/github-repos.txt` (una línea por `owner/repo`).

## Pasos

1. Corré el extractor en modo markdown (default: `auto` = watermark auto-sanable desde la última
   captura en `raw/github/`; clamp 2–14 días). Pasá N para una ventana explícita:
   ```bash
   python3 .claude/scripts/extract_github_prs.py --markdown "${1:-auto}"
   ```
   El script emite el `.md` FINAL directo a `raw/github/<fecha>.md` por cada fecha con actividad —
   agrupado por `## owner/repo` (orden descendente por número de PR), sentinel `<!-- pr: owner/repo#N -->`
   de idempotencia, mapeo de `state`/`draft`/`review_decision` y Jira keys entre paréntesis. También
   resuelve el merge: si el archivo de una fecha anterior a hoy ya existe, hace upsert por sentinel
   (preserva lo que no está en el bucket fresco); si es el archivo de **hoy**, lo regenera entero.
   Imprime por stdout `{"markdown": true, "written": [...], "dates": [...]}`.

   Si el script devuelve `{"error": "gh_not_authenticated", ...}` o falla, logueá y terminá
   sin error: este es un paso Tier 2 / best-effort.

2. Confirmá que escribió: revisá `written` en la salida (o `git status`/`ls` sobre
   `raw/github/<fecha>.md` para cada fecha en `dates`). Si escribió y el exit code fue 0, marcá el
   tier (`pipeline_checkpoint.py mark <pipeline> github regenerated "<detalle>"`). Si falló o no
   escribió nada, NO marques el tier — dejá que el fallback (renderizar a mano desde el JSON, ver
   abajo) se ocupe.

3. **Fallback manual** (solo si el script falla, p.ej. `gh` no autenticado a mitad de corrida, o un
   caso que el script no contempla): corré el extractor en modo JSON —
   `python3 .claude/scripts/extract_github_prs.py "${1:-auto}"` — y renderizá vos el `.md` siguiendo
   el mismo formato de arriba. Estructura del JSON: `cutoff_date`, `days`, `repos` (metadatos);
   `dates` (fechas con actividad); `by_date[<fecha>][<repo>]` = lista de PRs, cada uno con `number`,
   `title`, `state` (`open`/`closed`/`merged`), `author`, `branch`, `jira_keys`, `url`, `updated_at`,
   `merged_at`, `is_draft`, `review_decision`, `labels`. Es captura cruda: NO la edites como bitácora;
   es el insumo para `/bitacora`.

4. Informá una línea por fecha: `raw/github/<fecha>.md — <N> PRs (<repos>)`.
   Si `gh` no estaba disponible: `capturar-github: gh no autenticado, skip.`
