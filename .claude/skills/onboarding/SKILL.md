---
name: onboarding
description: Configura el second brain por primera vez. Corré esta skill apenas clonás el template — pregunta qué fuentes vas a capturar (proponiendo las existentes), tu zona horaria, idioma, prefijo de Jira y si querés automatizar el pipeline; después reemplaza los placeholders en todo el vault, escribe la config, opcionalmente instala el cron, y corre una primera captura de prueba. Usar para "onboarding", "configurar el vault", "setup inicial", "arrancar de cero".
---

# onboarding — setup guiado del second brain

Esta skill lleva a un usuario nuevo de un template recién clonado a un vault funcionando y personalizado.
Es **interactiva y conversacional**: preguntá, confirmá, y recién entonces escribí. No toques `raw/` ni
pises trabajo real: si detectás que el vault ya está en uso (hay capturas propias en `raw/`, o los
placeholders ya no están), avisá que parece configurado y preguntá si quiere re-correr el setup igual.

## 0. Detección de primera vez

Chequeá si el template todavía tiene los placeholders sin reemplazar:
```bash
grep -rl "tu-usuario@ejemplo.com\|#tu-canal\|PROJ-NNN" .claude/skills/ CLAUDE.md 2>/dev/null | head
```
Si hay matches → es un template fresco, seguí. Si no hay ninguno → ya está configurado: confirmá con
el usuario antes de re-aplicar nada.

## 1. Relevá las preferencias (una sola tanda de preguntas)

Usá **AskUserQuestion** con estas cuatro preguntas (batch), proponiendo las opciones existentes:

1. **Fuentes** (multiSelect) — "¿Qué fuentes vas a capturar?" Opciones (todas las que trae el template):
   - **Claude Code** — digest de tus sesiones (local, sin dependencias). *Recomendado.*
   - **Granola** — resúmenes de meetings vía el MCP de Granola (macOS + tier con MCP).
   - **Slack** — DMs/menciones/hilos vía el MCP de Slack (claude.ai).
   - **Google Calendar** — agenda del día vía el MCP de Google Calendar (claude.ai).
   - **GitHub** — PRs recientes vía `gh` CLI.
   - **Documentos / URLs** — ingesta manual con `/ingest` (markitdown + `gog`).
2. **Zona horaria e idioma** — "¿En qué zona horaria trabajás y en qué idioma querés el vault?"
   (ej. `America/Buenos_Aires` / español rioplatense; `Europe/Madrid` / español; `America/New_York` /
   inglés). El default del template es `America/Buenos_Aires` + español rioplatense.
3. **Gestor de tickets** — "¿Usás Jira (u otro tracker con keys tipo `ABC-123`)?" Opciones:
   - Sí, con prefijo `____` (pedí el prefijo, ej. `ABC`).
   - No uso tickets (el vault omite todo lo de Jira).
4. **Automatización** — "¿Querés que el pipeline corra solo?" Opciones:
   - Sí, instalar el cron (launchd, macOS) — corre pipeline diario + refresh horario + trigger post-meeting.
   - No, lo corro a mano con `/pipeline-diario`.

Después, **en conversación** (no hace falta AskUserQuestion), pedí lo que falte según lo elegido:
- Si eligió **GitHub**: qué repos trackear (formato `OWNER/REPO`, uno o varios).
- Si eligió **Slack**: qué canales le interesan (opcional; sirve para los ejemplos de la skill).
- El **nombre** con el que se lo referencia en la bitácora (opcional; default: sin nombre, tercera persona).

## 2. Aplicá la config (reemplazá placeholders)

Con las respuestas, hacé los reemplazos en todo el vault. Confirmá el plan en una línea antes de escribir.

- **Zona horaria** → reemplazá `America/Buenos_Aires` por la elegida en los dos extractores
  (`.claude/scripts/extract_claude_sessions.py` y `extract_github_prs.py`, constante `LOCAL_TZ`) y en
  `pipeline_checkpoint.py`. También en `CLAUDE.md`.
- **Idioma** → si NO es español rioplatense, ajustá la línea de idioma en `CLAUDE.md` (sección Propósito y
  regla final) y en la skill `/bitacora`. El template está escrito en español; si el usuario quiere el
  vault en otro idioma, dejá las skills como están (son instrucciones para el agente) pero cambiá la
  **regla de idioma de salida** para que las notas se generen en el idioma pedido.
- **Prefijo de Jira** → reemplazá `PROJ` / `PROJ-NNN` / `project = PROJ` por el prefijo real
  (`grep -rl "PROJ" .claude/skills CLAUDE.md`). Si el usuario NO usa tickets, quitá o neutralizá las
  menciones de Jira (dejá el vault funcionando sin sync de tickets — las skills degradan sin el MCP de
  Atlassian igual).
- **Email** → reemplazá `tu-usuario@ejemplo.com` por el suyo (lo usan `capturar-slack` e `ingest`).
- **Canales de Slack** → reemplazá `#tu-canal` por los que haya dado (o dejalo genérico si no dio).
- **Repos de GitHub** → escribí `.claude/config/github-repos.txt` con un `OWNER/REPO` por línea.
- **Nombres de repos locales** (opcional) → en `extract_claude_sessions.py`, la lista `KNOWN_REPOS` es
  solo cosmética (nombres lindos para los proyectos). Poné los nombres de sus repos o dejala.
- **Fuentes NO elegidas** → NO borres sus skills (quedan disponibles). En `CLAUDE.md`, dejá anotado en
  una línea qué fuentes están activas, para que el pipeline sepa cuáles correr. Las que no use degradan
  solas (sin el MCP conectado, ese tier se saltea sin romper nada).

## 3. Limpiá el contenido de ejemplo

El template trae páginas **sintéticas** de ejemplo (empresa y personas inventadas) para mostrar el formato:
`wiki/personas/ana-perez.md`, `wiki/proyectos/pipeline-ingesta.md`, `wiki/sistemas/snowflake.md`,
`wiki/decisiones/…`, `wiki/biblioteca/…`, más una `bitacora/` y un `todos/` de muestra.

Preguntá al usuario: **¿borro el contenido de ejemplo o lo dejás de molde?** Si dice borrar, eliminá esas
páginas de ejemplo (dejá los `.gitkeep`, `wiki/index.md`, `wiki/log.md` y `wiki/_taxonomia.md`), y reseteá
`wiki/index.md` a un índice vacío. La taxonomía (`wiki/_taxonomia.md`) trae vocabulario de ejemplo de Data
Engineering: sugerile adaptarla a su dominio.

## 4. Conectores y dependencias (avisá, no instales a ciegas)

Según las fuentes elegidas, decile qué le falta (no lo instales vos salvo que lo pida):
- **Granola/Slack/Calendar/Atlassian** → conectar el MCP correspondiente en claude.ai (`claude mcp add …`
  o desde la UI). Las skills degradan con gracia si no están.
- **GitHub** → `gh auth login`.
- **`/ingest`** → `markitdown` (`uv tool install markitdown`), y `gog` para Google Suite.
- **Automatización** → si eligió el cron, corré `zsh .claude/launchd/install.sh` (macOS; resuelve solo la
  ruta del vault y el binario `claude`). Si no, recordale `claude -p "/pipeline-diario"`.

## 5. Primera corrida + backup

- Configurá el remoto si todavía no está: `git remote -v` → si falta, pedile la URL de su repo **privado**
  y `git remote add origin <url>`.
- Corré una primera captura para validar: `/capturar-claude` (siempre anda, sin dependencias) y, si eligió
  otras fuentes con sus conectores listos, `/pipeline-diario` completo.
- `/backup` para dejar el primer commit.

## 6. Cierre

Resumí qué quedó configurado (fuentes activas, zona horaria, Jira, automatización sí/no) y remití al
`README.md` para el detalle. Recordá la regla de privacidad: el repo va **privado**, nunca pegar secretos
en una página (referenciar dónde viven, no el valor).
