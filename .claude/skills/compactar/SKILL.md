---
name: compactar
description: Compacta la bitácora en resúmenes temporales (semanal/mensual) y promueve el conocimiento durable a páginas de wiki. En modo diario (event-driven, sin resúmenes temporales) actualiza Interacciones + sync Jira y stagea candidatos para revisión. Usar para "resumen semanal", "resumen del mes", "compactá la semana", "promover gold diario", o en el pipeline. Hierarchical temporal summarization (log compaction de notas).
---

# compactar — compactación temporal + promoción a wiki

Hace *hierarchical temporal summarization*: bitácoras diarias → resumen semanal → resumen mensual,
y promueve hechos durables a `wiki/`. Uso: `/compactar semanal`, `/compactar mensual` o `/compactar diario`.

## Modo semanal (`/compactar semanal [YYYY-Www]`)
1. Determiná la semana ISO (default: la semana actual). Calculá el rango de fechas:
   ```bash
   date +%G-W%V        # semana ISO actual, ej 2026-W22
   ```
2. Leé las bitácoras de `bitacora/` que caen en esa semana.
3. Escribí `resumenes/semanal/<YYYY-Www>.md`:
   ```markdown
   ---
   semana: <YYYY-Www>
   rango: <YYYY-MM-DD> a <YYYY-MM-DD>
   tags: [resumen, semanal]
   ---

   # Semana <YYYY-Www>

   ## Logros
   - <hito> ([[proyecto]], <JIRA-KEY>)

   ## Decisiones
   - <decisión tomada> → considerar promover a [[wiki/decisiones/...]]

   ## Hilos abiertos / en curso
   - <qué quedó pendiente o esperando a alguien>

   ## TODOs
   - abiertos: N · cerrados esta semana: M (de todos.base)
   ```

4. Al final del resumen semanal, corré `/limpiar-todos 14` para eliminar los TODOs completados
   con más de 14 días de antigüedad. Reportá el resultado en el resumen (`## TODOs`).

## Modo mensual (`/compactar mensual [YYYY-MM]`)
1. Default: mes actual (`date +%Y-%m`).
2. Leé los resúmenes de `resumenes/semanal/` de ese mes.
3. Escribí `resumenes/mensual/<YYYY-MM>.md` con la misma estructura, a mayor altitud (tendencias del
   mes, decisiones estructurales, evolución de proyectos).

## Modo diario (`/compactar diario`)

Hace SOLO la mitad **event-driven** de la promoción a gold. **No** genera `resumenes/`. El pipeline
diario lo invoca entre `/todos` y `/backup` como paso best-effort.

**Derivá la ventana de trabajo** de los archivos presentes en `raw/` (misma lógica que `/bitacora`
paso 1) — no hardcodeés today/today-1; no asumas que `raw/calendar/<ayer>.md` existe.

### AUTO — escribe directo a `wiki/`

Ejecutá los bloques idempotentes de esta skill (sus reglas completas están en las secciones de
más abajo; acá se referencian, no se duplican):

1. **`## Interacciones`** (ver "Timeline de contacto por persona" más abajo): actualizá la sección
   en páginas de persona existentes y creá página si hubo 1-1 sin página. Regla clave:
   **Slack-only con persona sin página → NO crear página** (solo se suma a fichas que ya existen).
   Sin transcript → "sin transcript capturado". Dedupe por `(fecha, tipo)` = idempotente.
2. **Sync de estado Jira** (ver "Sincronización de `estado` con Jira" más abajo): actualizá
   `estado:` en proyectos **solo si cambió**. Degrada en silencio si Atlassian no está.
3. **Sync `## PRs recientes` en `wiki/proyectos/`** (ver "PRs recientes por proyecto" más abajo):
   actualizá la sección con los PRs abiertos + mergeados recientes de cada proyecto. Best-effort:
   si `raw/github/` no existe o está vacío, salteá.

### STAGE — materializa notas de revisión en `candidatos-gold/`

**No** escribas a `wiki/` para estas entidades — son candidatos que requieren juicio humano:
- **Decisiones nuevas** detectadas en la bitácora/raw del window: creá nota con el *porqué* ya
  redactado en el cuerpo (capturás lo valioso de inmediato; el humano confirma título/slug al drenar).
- **Páginas nuevas** de persona/sistema/proyecto sujetas a la **regla de 2-3** (un solo día no
  alcanza para validar recurrencia).
- **Edits de conocimiento durable** a páginas existentes que requieren juicio contextual.

Cada candidato es una nota `candidatos-gold/<entidad>.md` con este frontmatter:
```yaml
tags: [candidato-gold]
estado: pendiente          # pendiente | hecho | descartado
tipo: persona|sistema|proyecto|decision
entidad: <slug de la página destino>
origen: raw/granola/...    # o bitacora/YYYY-MM-DD.md
created: YYYY-MM-DD
```
- **Dedupe por `entidad`+`tipo`** (no por fecha de corrida) → la window ayer+hoy no duplica.
- **Update-only**: si la nota del candidato ya existe, actualizá el cuerpo, no creés otra.

### Cierre condicional del modo diario
- Actualizá `wiki/index.md` y appendeá a `wiki/log.md` **solo si** AUTO tocó al menos una página
  real de `wiki/`. Corrida no-op o que solo stageó candidatos → no toca `index.md` ni `log.md`.
- Bumpear `last_updated:` en una ficha de persona **solo si** el contenido de `## Interacciones`
  efectivamente cambió (evitar churn de diffs espurios en cada corrida).

### Reglas headless para el modo diario
- Nunca pedís confirmación interactiva ni usás hooks que devuelvan `ask`. Si un sub-paso falla →
  loguealo y seguí. El paso nunca debe abortar el pipeline.
- Resumen de 1 línea al final: qué hizo AUTO, qué stageó, qué saltó.

## Cadencia y umbral de promoción a wiki

Las capas tienen cadencias DISTINTAS — no promuevas al wiki por reloj:
- `resumenes/` (semanal/mensual) es **time-driven**: se genera por calendario (lunes / día 1).
- `wiki/` es **event-driven**: se promueve cuando un hecho cruza el **umbral de durabilidad**.

El momento natural de promover es **durante esta compactación**. Reglas:
- **Regla de 2-3**: una entidad (persona/sistema/proyecto) que aparece en **≥2-3 días o semanas** →
  merece página. Mención única → se queda en la bitácora, NO se promueve (evitar *sprawl*).
- **Decisiones = inmediato**: una decisión de arquitectura/naming/política se promueve a
  `wiki/decisiones/` apenas ocurre (no esperar la compactación) — perder el *porqué* es caro.
- **Update, no append**: si la entidad ya tiene página, se **actualiza**, nunca se duplica.

## Promoción a wiki (en ambos modos)
Aplicando la regla de arriba, los **hechos durables** se promueven/actualizan en `wiki/`:
- Decisión → `wiki/decisiones/<FECHA>-<slug>.md`.
- Persona recurrente → `wiki/personas/<nombre>.md`.
- Sistema/herramienta recurrente → `wiki/sistemas/<slug>.md`.
- Proyecto con avance → actualizá `wiki/proyectos/<slug>.md` (frontmatter `estado`, `epic`,
  `last_updated`; `proyectos.base` lo refleja).
Conectá todo con `[[wikilinks]]`. Seguí el formato de página del `CLAUDE.md`.

### Timeline de contacto por persona — `## Interacciones`

Para cada persona conocida (`wiki/personas/`), consolidá sus **1-1s y Slack curado** del período
en la sección `## Interacciones` de su ficha. Esta sección convierte la ficha en un CRM liviano.

**Fuentes a leer:**
- `raw/calendar/<fecha>.md` — buscá líneas con el marcador `tipo:1-1` (ej.
  `grep "tipo:1-1" raw/calendar/*.md`). Cada match es un 1-1 con la persona indicada en
  `persona:[[wikilink]]`.
- `raw/slack/<fecha>.md` — buscá headers `## DM con <Nombre>` y `## Group DM con …`; identificá
  la persona por nombre/alias contra `wiki/personas/`. Solo intercambios **sustantivos** (pedidos,
  acuerdos, decisiones, accionables); descartá ruido (`"yes"`, `"listoo"`, etc.).

**Reglas de promoción:**
- **1-1 fuerza crear/actualizar la página de persona** — excepción a la regla de 2-3. Un 1-1
  agendado ya es señal de relación recurrente. Si la página no existe, creala con el formato
  mínimo (Resumen derivable del Contexto disponible + `## Interacciones` vacía inicial).
- **Slack NO fuerza página** — solo se suma a fichas que ya existen (por 1-1 o por regla de 2-3).
  Slack-only con persona sin página → se queda en `raw/` + bitácora.
- **Curación de Slack** — resumí en 1 línea por día; nunca verbatim. Múltiples intercambios del
  mismo día → una entrada consolidada. El verbatim queda en `raw/slack/` (bronze).
- **Dedupe por `(fecha, tipo)`** — si ya existe una entrada para esa clave, actualizala (update,
  no append). Re-correr la compactación es idempotente.

**Formato de la sección `## Interacciones`:**
```markdown
## Interacciones
- **2026-06-15** · 1-1 — Repaso de prioridades y harness local; se acordó X (PROJ-170). (fuente: raw/calendar/2026-06-15.md, raw/granola/2026-06-15-1on1-ana-perez.md)
- **2026-06-01** · 1-1 — Agendado con doc "Guía para tu reunión de 1:1"; sin transcript capturado. (fuente: raw/calendar/2026-06-01.md)
- **2026-06-01** · Slack — Consultó por el estado de una captura y coordinó una sync previa. (fuente: raw/slack/2026-06-01.md, ts: 1780327738)
```

Reglas del formato:
- Orden **descendente** (más reciente arriba).
- `**YYYY-MM-DD** · <tipo>` con `tipo ∈ {1-1, Slack}`.
- **1-1:** cita `raw/calendar/<fecha>.md` + `raw/granola/<slug>.md` si hubo resumen/transcript del
  meeting. Sin captura del meeting → decirlo: "sin resumen capturado".
- **Slack:** cita `raw/slack/<fecha>.md` + `ts` del mensaje clave.
- Jira keys inline `(PROJ-n)` si el intercambio tocó un ticket.

**Ubicación dentro de la ficha de persona:** después de `## Contexto` y antes de `## Relacionado`.
Bumpear `last_updated:` del frontmatter en cada escritura.

## Sincronización de `estado` con Jira (proyectos) — Tier 2, best-effort

Mantiene el `estado:` de `wiki/proyectos/` alineado con Jira (PROJ). Corre dentro de esta compactación.

1. Juntá los proyectos a sincronizar: cada página de `wiki/proyectos/*.md` que tenga `epic:` (la
   épica de la iniciativa; o `ticket:` como fallback legacy — key `PROJ-<n>`) y **no** tenga
   `jira_sync: false` (override manual para proyectos que querés fijar a mano,
   ej. una plataforma viva cuyos tickets ya están cerrados).
2. Una sola query JQL con los keys juntos, pidiendo **solo** el campo `status` (traer la descripción
   completa revienta el límite de tokens — no la pidas):
   ```
   searchJiraIssuesUsingJql(jql="project = PROJ AND key in (PROJ-a, PROJ-b, …)", fields=["status"])
   ```
3. Mapeá el status de Jira → `estado` del wiki:
   - `statusCategory.key == "done"` (ej. *Finalizada*) → `cerrado`
   - status que matchea `/block/i` (ej. *Blocked*) → `pausado`
   - cualquier otro abierto (*Tareas por hacer*, *En curso*) → `activo`
4. Para cada proyecto donde el `estado` calculado ≠ el actual: actualizá `estado:` + `last_updated:` en
   el frontmatter. `proyectos.base` (agrupa por `estado`) lo refleja solo.
5. Reportá los cambios: una línea por proyecto en el resumen (`## Estado de proyectos (sync Jira)`) y en
   `wiki/log.md`. Si no hubo cambios, decilo.

**Progreso (opcional)**: para una épica, `searchJiraIssuesUsingJql(jql="parent = PROJ-<épica>", fields=["status"])`
cuenta hijos done/total y permite anotar el avance de la iniciativa en el resumen.

**Degradación**: si el MCP de Atlassian no está disponible en la sesión, salteá este paso y dejalo
anotado (no es bloqueante). Proyectos sin `epic:` ni `ticket:` (ej. POCs nuevos) se ignoran.

## PRs recientes por proyecto — `## PRs recientes` (paso 3 del bloque AUTO)

Mantiene una sección `## PRs recientes` en cada página de `wiki/proyectos/` con los PRs
vinculados a esa iniciativa. La fuente es `raw/github/` (última semana de capturas).

**Matching PR → proyecto:** señal primaria = la key Jira en `headRefName` (branch) o `title` del PR
coincide con el `epic:` o `ticket:` de la página. Ej: branch `feat/PROJ-204/nombre-feature`
→ mapea a la página con `epic: PROJ-204`. Si un PR no tiene key visible en branch/título, no
se asigna (demasiado ambiguo para automatizar).

**Qué incluir:**
- PRs **abiertos** (state: open/draft) vinculados al proyecto — siempre.
- PRs **mergeados** en los últimos 7 días — incluir para tener el historial reciente.
- PRs **cerrados sin merge** — excluir (descartados, no aportan valor).

**Formato de la sección:**
```markdown
## PRs recientes
<!-- github-prs-sync: YYYY-MM-DD -->
- **[#N](url)** · `<branch>` · **<estado>** · @<autor> *(repo)*
- **[#N](url)** · `<branch>` · **mergeado** · @<autor> *(repo)*
```
Donde `estado` sigue el mismo vocabulario que `raw/github/`: **abierto**, **draft**, **mergeado**.
Orden: primero los abiertos (por número desc), luego los mergeados recientes.

**Idempotencia:** el sentinel `<!-- github-prs-sync: YYYY-MM-DD -->` es la marca de la última
actualización. Al correr, reemplazá la sección entera (desde `## PRs recientes` hasta el
siguiente `##` o el EOF). Bumpear `last_updated:` del frontmatter **solo si** el contenido
efectivamente cambió (comparar con el anterior antes de escribir).

**Degradación:** si la página no tiene `epic:` ni `ticket:`, o si `raw/github/` no existe
o no tiene archivos de la última semana → salteá esa página silenciosamente.

## Drenado de candidatos-gold (en modos semanal/mensual)

Al final de cada compactación semanal/mensual, drenás la cola de candidatos staged por el modo diario:

1. Leé `candidatos-gold/*.md` con `estado: pendiente`.
2. Para cada candidato, **aplicá la regla de 2-3** con la evidencia acumulada en la semana/mes:
   - Si la entidad aparece en ≥2-3 días distintos → promueve a `wiki/`.
   - Si no alcanzó el umbral → marcá `estado: descartado` con una línea de razón en el cuerpo.
3. **Antes de promover, verificá si la página destino ya existe** en `wiki/`:
   - Si existe (el humano la promovió a mano) → marcá `estado: hecho` sin reescribir la wiki.
   - Si no existe → creá la página siguiendo el formato de `CLAUDE.md`, con el contenido
     redactado en el cuerpo del candidato como punto de partida.
4. Actualizá `wiki/index.md` y appendeá a `wiki/log.md` por cada página creada/modificada.
5. Update-only en las notas de candidato: nunca borrés, solo actualizás `estado`.

## Cierre (siempre)
- Actualizá `wiki/index.md` con las páginas nuevas/modificadas (una línea + descripción).
- Appendeá a `wiki/log.md`: fecha, qué se compactó, qué páginas tocó.
- No toques `raw/` ni reescribas las bitácoras (son el insumo, quedan como están).
