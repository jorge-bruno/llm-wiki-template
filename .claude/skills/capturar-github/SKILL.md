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

1. Corré el extractor (default: `auto` = watermark auto-sanable desde la última captura en
   `raw/github/`; clamp 2–14 días). Pasá N para una ventana explícita:
   ```bash
   python3 .claude/scripts/extract_github_prs.py "${1:-auto}"
   ```
   Si el script devuelve `{"error": "gh_not_authenticated", ...}` o falla, logueá y terminá
   sin error: este es un paso Tier 2 / best-effort.

2. Parseá el JSON. Estructura:
   - `cutoff_date`, `days`, `repos`: metadatos de la corrida.
   - `dates`: lista de fechas con actividad.
   - `by_date[<fecha>][<repo>]` = lista de PRs. Cada PR tiene: `number`, `title`, `state`
     (`open`/`closed`/`merged`), `author`, `branch`, `jira_keys` (regex `PROJ-NNN` del branch+título),
     `url`, `updated_at`, `merged_at`, `is_draft`, `review_decision`, `labels`.

3. **Por cada fecha en `dates`**, escribí/actualizá `raw/github/<fecha>.md`:
   ```markdown
   > **Fuente**: GitHub PRs (`gh`) · **Capturado**: <HOY> · repos: <lista> · ventana: <N> día(s)

   # GitHub PRs — <fecha>

   ## <owner>/<repo>

   <!-- pr: <owner>/<repo>#<N> -->
   - **PR #<N>** · `<branch>` · **<state>** · @<author> — <título> (<PROJ-KEY> si hay) *(fuente: [#<N>](<url>))*
   ```
   Reglas de renderizado:
   - Agrupá por `## owner/repo`. Dentro de cada repo, ordená por número de PR descendente.
   - El comentario `<!-- pr: owner/repo#N -->` en la línea anterior al bullet es el **sentinel de
     idempotencia**: al mergear días previos, buscá ese patrón para saber qué PRs ya están.
   - Para `state`: `open` → **abierto**; `merged` → **mergeado**; `closed` → **cerrado**.
   - Si `is_draft` es true → `**draft**` en vez del state.
   - Si `review_decision` es `APPROVED` → añadí `✓ aprobado` al lado.
   - Si `review_decision` es `CHANGES_REQUESTED` → añadí `⚑ cambios solicitados`.
   - Keys de Jira entre paréntesis: `(PROJ-NNN)`. Si hay varias, listas: `(PROJ-221, PROJ-224)`.
   - Es captura cruda: NO la edites como bitácora; es el insumo para `/bitacora`.

4. **Idempotencia / merge**:
   - Si `raw/github/<fecha>.md` **no existe** → crealo desde el bucket.
   - Si **ya existe** y es un día **anterior a hoy** → **mergeá**: leé el archivo, extraé los
     sentinels `<!-- pr: ... -->` ya presentes, y agregá solo los PRs que aún no están. Preservá
     el texto curado existente (no regeneres desde cero un archivo de un día previo).
   - Si es el archivo de **hoy** → regeneralo entero (captura viva que crece durante el día).

5. Informá una línea por fecha: `raw/github/<fecha>.md — <N> PRs (<repos>)`.
   Si `gh` no estaba disponible: `capturar-github: gh no autenticado, skip.`
