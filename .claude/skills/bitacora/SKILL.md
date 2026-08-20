---
name: bitacora
description: Genera la bitácora diaria del second brain (bitacora/YYYY-MM-DD.md) sintetizando las capturas de raw/ del día (Claude, Granola, Slack, Calendar, docs, GitHub). Agrupada por proyecto, en español pasado, con dedupe contra días previos y detección de pendientes. Usar para "armar la bitácora", "nota del día", o dentro del pipeline diario.
---

# bitacora — síntesis diaria (silver)

Sintetiza las capturas crudas de `raw/` en una nota diaria curada en `bitacora/<FECHA>.md`.
Es el corazón del nivel silver. Modela el formato de la skill de referencia `daily-notes` pero
sobre todas las fuentes del vault.

## Pasos

1. Fecha: `FECHA=$(date +%F)`. (Si el usuario pide "la de ayer", usá today-1.)
   - **En el pipeline diario, regenerá la bitácora de CADA fecha que las capturas tocaron** (típico:
     ayer + hoy). Como las capturas atribuyen por fecha del evento, el trabajo de anoche recién se
     captura a la mañana siguiente y aterriza en el `raw/` de **ayer** → la bitácora de ayer hay que
     completarla hoy. Mirá las fechas presentes en `raw/claude/` y `raw/slack/` de la ventana.
2. Asegurá las capturas del día: si no existen, corré `/capturar-claude` y `/capturar-granola`
   (y `/capturar-slack`, `/capturar-calendar`, `/capturar-github` si están disponibles). Luego
   **leé** las capturas del día en `raw/{claude,granola,slack,calendar,github,docs}/` que
   correspondan a `<FECHA>`.
3. Leé las últimas ~4 bitácoras previas en `bitacora/` para el dedupe.
4. Sintetizá `bitacora/<FECHA>.md`:
   ```markdown
   ---
   fecha: <FECHA>
   tags: [bitacora]
   ---

   # 🗓️ <FECHA — ej: 31 de mayo de 2026>

   ### <Proyecto / Área>
   - <qué pasó, en pasado> (<JIRA-KEY> si aplica) (fuente: raw/.../...)
     - <detalle si el bullet supera ~120 chars>

   ### <Otro proyecto>
   - ...

   ## Pendientes detectados
   - <accionable 1> — proyecto <X>, origen <fuente>
   - <accionable 2>
   ```
   Reglas:
   - **Agrupá por proyecto/área**, NO por herramienta. Nunca menciones las herramientas de captura
     (agentes de IA, sistemas internos, etc.) como si fueran el proyecto en sí.
   - Español argentino, **tiempo pasado** ("Se implementó…", "Se coordinó con [[ana-perez]]…").
   - `###` por proyecto (nunca bold), bullets `-`. Linkeá personas/sistemas con `[[wikilinks]]`.
   - Citá la fuente de cada bullet (`(fuente: raw/...)`, Jira key, ts de Slack).
   - **Dedupe** vs. días previos: por Jira key (primario) y substring (fallback). Si el entregable ya
     se registró → omitilo; si hay trabajo incremental → describí solo el delta.
   - Si tras dedupe un proyecto queda sin bullets, no rendericés su `###`.
   - **PRs de `raw/github/`**: asigná cada PR al proyecto que corresponda usando la key Jira del
     branch/título como señal primaria (ej. `feat/PROJ-204/...` → proyecto PROJ-204). PRs sin key
     visible agrupalos bajo `### <nombre-repo>` solo si tienen movimiento sustantivo (merge,
     aprobación, cambios pedidos) — omití los que solo tuvieron un push. Citá como
     `(fuente: raw/github/<FECHA>.md)`. No repitas PRs que ya aparecieron en la fuente Slack o
     Claude del mismo día.
5. La sección **"Pendientes detectados"** es el insumo para `/todos`: listá accionables abiertos
   detectados hoy (no los materialices como notas acá; eso lo hace `/todos`).
6. Idempotencia: la nota se llama por fecha; re-correr el mismo día la regenera con lo capturado.
7. Ofrecé al usuario: correr `/todos` para materializar los pendientes, y promover hechos durables
   al wiki. Si hubo **1-1s** hoy (marcador `tipo:1-1` en `raw/calendar/`) o **DMs sustantivos**
   (pedidos, acuerdos, accionables) en `raw/slack/`, mencionalo: "Hay interacciones del día listas
   para promover a `## Interacciones` de las fichas de persona vía `/compactar`." No escribas al
   wiki directamente — eso lo hace `/compactar`.
