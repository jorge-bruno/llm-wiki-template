# Second Brain — LLM Wiki (template)

Un **second brain** mantenido por [Claude Code](https://claude.com/claude-code): captura tu trabajo
diario desde varias fuentes (Claude Code, Granola, Slack, Google Calendar, documentos), lo sintetiza
en una bitácora diaria, lo compacta en resúmenes semanales/mensuales y promueve el conocimiento
durable a un wiki interconectado. Es a la vez un **vault de [Obsidian](https://obsidian.md)**.

Inspirado en el patrón *LLM Wiki* de Andrej Karpathy, ajustado a un flujo de Data Engineering.
Arquitectura **medallion** (bronze → silver → gold): ver `CLAUDE.md` para el detalle conceptual.

```
raw/        bronze  · captura cruda e inmutable de cada fuente
bitacora/   silver  · síntesis diaria por proyecto
wiki/       gold    · páginas curadas e interlinkadas
resumenes/  gold    · rollups semanales / mensuales
todos/              · un archivo por TODO (alimenta todos.base)
```

---

## Cómo funciona (el loop diario)

`/pipeline-diario` orquesta todo de punta a punta (lo dispara el cron, o lo corrés a mano):

1. **Captura** — `/capturar-claude`, `/capturar-granola` (Tier 1, siempre) + `/capturar-slack`,
   `/capturar-calendar` (Tier 2, best-effort) → todo a `raw/`.
2. **Síntesis** — `/bitacora` arma la nota del día agrupada por proyecto.
3. **TODOs** — `/todos` materializa los pendientes detectados.
4. **Backup** — `/backup` commitea y pushea (esto es lo que **preserva los transcripts de Granola**,
   que el plan free borra a los ~7 días).

Semanal/mensual: `/compactar semanal|mensual` hace el rollup y promueve hechos durables al wiki.

Hacé preguntas en lenguaje natural: Claude lee `wiki/index.md`, sigue los wikilinks y te responde
citando las páginas.

---

## Prerequisitos

| Herramienta | Para qué | Obligatorio |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) | El agente que mantiene el vault | **Sí** |
| Python 3.10+ | Extractores (`extract_claude_sessions.py`, `granola_extract.py`) | **Sí** |
| [Obsidian](https://obsidian.md) | Ver el vault, los grafos y los `.base` | Recomendado |
| [Granola](https://granola.ai) (macOS) | Captura de transcripts de meetings | Opcional |
| `markitdown` (`uv tool install markitdown`) | `/ingest` de PDFs, docx, pptx, etc. | Opcional |
| `gog` | `/ingest` de Google Docs/Sheets/Slides/Drive | Opcional |
| `ffmpeg` (`brew install ffmpeg`) | Transcripción de audio/video en `/ingest` | Opcional |
| MCP de Slack / Google Calendar / Atlassian (claude.ai) | Captura de Slack/Calendar, sync de Jira | Opcional |

> **Nota:** la captura de Granola y el cron (launchd) son **macOS-only**. El resto es portable.

---

## Setup

### 1. Cloná y abrí el vault
```bash
git clone <tu-repo> second-brain && cd second-brain
```
Abrí la carpeta como vault en Obsidian (opcional pero recomendado: instalá el core plugin **Bases**).

### 2. Personalizá los placeholders
El template viene con placeholders genéricos. Buscalos y reemplazalos por lo tuyo:

| Placeholder | Qué es | Dónde |
|---|---|---|
| `PROJ` / `PROJ-NNN` | Tu key de proyecto en Jira (ej. `ABC`) | skills, `CLAUDE.md`, taxonomía |
| `tu-usuario@ejemplo.com` | Tu email (Slack, `gog`) | `capturar-slack`, `ingest` |
| `#tu-canal` | Tus canales de Slack de interés | `capturar-slack`, `ingest` |
| UTC-3 / Buenos Aires | Tu zona horaria | `LOCAL_TZ` en `extract_claude_sessions.py`, `ART` en `granola_extract.py` |

Las páginas de ejemplo (`wiki/`, `bitacora/`, `todos/`) son **sintéticas** (empresa y personas
inventadas) — borralas o usalas de molde. La taxonomía (`wiki/_taxonomia.md`) trae un vocabulario de
ejemplo de Data Engineering: adaptalo a tu dominio.

### 3. Venv para el extractor de Granola (macOS)
```bash
python3 -m venv .claude/scripts/granola-venv
.claude/scripts/granola-venv/bin/pip install -r .claude/scripts/requirements.txt
```
La primera vez que el extractor lee el Keychain (item *Granola Safe Storage*), macOS pide permiso:
dale **"Always Allow"** para que la captura headless funcione.

### 4. (Opcional) Cron diario/semanal/mensual con launchd (macOS)
```bash
zsh .claude/launchd/install.sh
```
`install.sh` resuelve solo la ruta del vault y el binario de `claude`, renderiza los plists y los
carga. Re-ejecutalo tras editar cualquier `.plist`. Sin cron, corré el pipeline a mano:
`claude -p "/pipeline-diario"`.

### 5. (Opcional) Conectá los MCP
Para Slack/Calendar/Jira, conectá los MCP correspondientes en claude.ai. Las skills Tier 2 degradan
con gracia si no están disponibles (no rompen el pipeline).

### 6. Configurá el remoto y backupeá
```bash
git remote add origin <tu-repo-privado>
claude -p "/backup"
```
⚠️ **Mantené el repo privado**: el vault contiene data confidencial (meetings, Slack, infra). Nunca
pegues secrets en una página — referenciá dónde viven, no el valor.

---

## Skills disponibles

| Skill | Qué hace |
|---|---|
| `/pipeline-diario` | Corre el loop diario completo (captura → bitácora → TODOs → backup). |
| `/capturar-claude` | Digest de sesiones de Claude Code → `raw/claude/`. |
| `/capturar-granola` | Transcripts de meetings desde el cache local cifrado → `raw/granola/`. |
| `/capturar-slack` | DMs/menciones/hilos relevantes → `raw/slack/`. |
| `/capturar-calendar` | Agenda del día → `raw/calendar/`. |
| `/ingest <fuente>` | Convierte archivo/URL a markdown (markitdown + `gog`). |
| `/bitacora` | Síntesis diaria por proyecto (silver). |
| `/compactar semanal\|mensual` | Rollup temporal + promoción a wiki (gold). |
| `/todos` | Genera/groomea TODOs desde el WIP, dedup contra Jira. |
| `/backup` | Commit + push del vault. |

---

## Créditos

Template derivado de un second brain personal. La idea original del patrón LLM Wiki es de
[Andrej Karpathy](https://github.com/karpathy). Adaptado para Data Engineering + Claude Code.
