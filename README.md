# Second Brain — LLM Wiki (template)

Un **second brain** mantenido por [Claude Code](https://claude.com/claude-code): captura tu trabajo
diario desde varias fuentes (Claude Code, Granola, Slack, Google Calendar, GitHub, documentos), lo
sintetiza en una bitácora diaria, lo compacta en resúmenes semanales/mensuales y promueve el
conocimiento durable a un wiki interconectado. Es a la vez un **vault de [Obsidian](https://obsidian.md)**.

Inspirado en el patrón *LLM Wiki* de Andrej Karpathy, ajustado a un flujo de Data Engineering.
Arquitectura **medallion** (bronze → silver → gold): ver `CLAUDE.md` para el detalle conceptual.

```
raw/        bronze  · captura cruda e inmutable de cada fuente
bitacora/   silver  · síntesis diaria por proyecto
wiki/       gold    · páginas curadas e interlinkadas
resumenes/  gold    · rollups semanales / mensuales
todos/              · un archivo por TODO (alimenta todos.base + kanban.html)
```

---

## Arranque rápido

```bash
git clone <tu-repo-privado> second-brain && cd second-brain
claude   # abrí Claude Code en la carpeta
```

Y adentro de Claude Code, corré:

```
/onboarding
```

`/onboarding` te hace unas pocas preguntas (qué fuentes vas a capturar, tu zona horaria, idioma,
prefijo de Jira, si querés automatizar el pipeline), **reemplaza los placeholders del template por lo
tuyo**, escribe la config, opcionalmente instala el cron y corre una primera captura de prueba. Es la
forma recomendada de hacer el template tuyo. El resto de este README es el detalle manual.

> Abrí también la carpeta como vault en Obsidian (opcional pero recomendado: activá el core plugin
> **Bases** para ver `todos.base` / `proyectos.base` / `biblioteca.base`).

---

## Cómo funciona (el loop diario)

`/pipeline-diario` orquesta todo de punta a punta (a mano, o lanzado por el cron):

1. **Captura** — `/capturar-claude` (siempre) + `/capturar-granola`, `/capturar-slack`,
   `/capturar-calendar`, `/capturar-github` (best-effort) → todo a `raw/`.
2. **Síntesis** — `/bitacora` arma la nota del día agrupada por proyecto.
3. **TODOs** — `/todos` materializa los pendientes detectados y groomea el board.
4. **Compactar** — `/compactar diario` actualiza Interacciones de personas + sync de Jira.
5. **Backup** — `/backup` commitea y pushea (esto es lo que **preserva los resúmenes de Granola**).

Intradía: `/refresh` re-corre una versión liviana tras cada meeting y por hora.
Semanal/mensual: `/compactar semanal|mensual` hace el rollup y promueve hechos durables al wiki.

Hacé preguntas en lenguaje natural: Claude lee `wiki/index.md`, sigue los wikilinks y te responde
citando las páginas.

---

## Prerequisitos

| Herramienta | Para qué | Obligatorio |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) | El agente que mantiene el vault | **Sí** |
| Python 3.10+ | Extractores (solo stdlib, sin dependencias) | **Sí** |
| [Obsidian](https://obsidian.md) | Ver el vault, los grafos y los `.base` | Recomendado |
| [Granola](https://granola.ai) + su MCP | Resúmenes de meetings | Opcional |
| `gh` CLI (`gh auth login`) | `/capturar-github` | Opcional |
| `markitdown` (`uv tool install markitdown`) | `/ingest` de PDFs, docx, pptx, etc. | Opcional |
| `gog` | `/ingest` de Google Docs/Sheets/Slides/Drive | Opcional |
| MCP de Slack / Google Calendar / Atlassian (claude.ai) | Captura de Slack/Calendar, sync de Jira | Opcional |

> **Nota:** el cron (launchd) es **macOS-only**. El resto es portable. Las fuentes opcionales degradan
> con gracia: si no conectás su MCP / CLI, ese paso se saltea sin romper el pipeline.

---

## Setup manual (si no usás `/onboarding`)

### 1. Personalizá los placeholders
El template viene con placeholders genéricos. Reemplazalos por lo tuyo:

| Placeholder | Qué es | Dónde |
|---|---|---|
| `PROJ` / `PROJ-NNN` | Tu prefijo de proyecto en Jira (ej. `ABC`) | skills, `CLAUDE.md` |
| `tu-usuario@ejemplo.com` | Tu email (Slack, `gog`) | `capturar-slack`, `ingest` |
| `#tu-canal` | Tus canales de Slack de interés | `capturar-slack`, `ingest` |
| `America/Buenos_Aires` | Tu zona horaria | `LOCAL_TZ` en los extractores + `pipeline_checkpoint.py`, `CLAUDE.md` |

Las páginas de ejemplo (`wiki/`, `bitacora/`, `todos/`) son **sintéticas** (empresa y personas
inventadas) — borralas o usalas de molde. La taxonomía (`wiki/_taxonomia.md`) trae un vocabulario de
ejemplo de Data Engineering: adaptalo a tu dominio.

### 2. Configurá los repos de GitHub (si usás `/capturar-github`)
Editá `.claude/config/github-repos.txt` con un `OWNER/REPO` por línea.

### 3. Conectá los MCP (opcional)
Para Slack/Calendar/Jira/Granola, conectá los MCP correspondientes en claude.ai. Las skills Tier 2
degradan con gracia si no están disponibles (no rompen el pipeline).

### 4. Configurá el remoto y backupeá
```bash
git remote add origin <tu-repo-privado>
claude -p "/backup"
```
⚠️ **Mantené el repo privado**: el vault contiene data confidencial (meetings, Slack, infra). Nunca
pegues secrets en una página — referenciá dónde viven, no el valor.

---

## Automatización (opcional, macOS)

Sin cron, corré el pipeline a mano: `claude -p "/pipeline-diario"`.

Con launchd:
```bash
zsh .claude/launchd/install.sh
```
`install.sh` resuelve solo la ruta del vault y el binario de `claude`, renderiza los plists y los
carga. Instala:
- **daily** — `/pipeline-diario` a la mañana.
- **refresh** — `/refresh` por hora (L-V) + trigger event-driven tras cada meeting (watcher de Granola).
- **weekly / monthly** — `/compactar semanal|mensual`.

Re-ejecutá `install.sh` tras editar cualquier `.plist`.

> **Split de modelo recomendado:** el trabajo mecánico (daily / refresh: captura + síntesis + dedupe)
> rinde bien con un modelo rápido; el juicio durable (weekly / monthly: drenar `candidatos-gold/`,
> promover a wiki) conviene en el modelo más capaz. Los wrappers corren con tu modelo por defecto;
> podés fijar el modelo por corrida editando el `-p` de cada wrapper (ej. `--model sonnet` /
> `--model opus`).

---

## Skills disponibles

| Skill | Qué hace |
|---|---|
| `/onboarding` | Setup guiado la primera vez (fuentes, zona horaria, Jira, placeholders). |
| `/pipeline-diario` | Corre el loop diario completo (captura → bitácora → TODOs → compactar → backup). |
| `/refresh` | Mini-pipeline intradía (más liviano; sin Calendar). |
| `/capturar-claude` | Digest de sesiones de Claude Code → `raw/claude/`. |
| `/capturar-granola` | Resúmenes de meetings vía MCP de Granola → `raw/granola/`. |
| `/capturar-slack` | DMs/menciones/hilos relevantes → `raw/slack/`. |
| `/capturar-calendar` | Agenda del día → `raw/calendar/`. |
| `/capturar-github` | PRs recientes (`gh`) → `raw/github/`. |
| `/ingest <fuente>` | Convierte archivo/URL a markdown (markitdown + `gog`). |
| `/bitacora` | Síntesis diaria por proyecto (silver). |
| `/compactar diario\|semanal\|mensual` | Compactación temporal + promoción a wiki (gold). |
| `/todos` | Genera/groomea TODOs desde el WIP, dedup contra Jira; regenera `kanban.html`. |
| `/daily` | Status del standup → DM de Slack. |
| `/health-check` | Diagnóstico del estado del vault. |
| `/limpiar-todos` | Borra los TODOs terminales viejos. |
| `/backup` | Commit + push del vault. |

---

## Créditos

Template derivado de un second brain personal. La idea original del patrón LLM Wiki es de
[Andrej Karpathy](https://github.com/karpathy). Adaptado para Data Engineering + Claude Code.
