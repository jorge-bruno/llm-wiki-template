---
name: compactar
description: Compacta la bitácora en resúmenes temporales (semanal/mensual) y promueve el conocimiento durable a páginas de wiki. Usar para "resumen semanal", "resumen del mes", "compactá la semana", o en el pipeline semanal/mensual. Hierarchical temporal summarization (log compaction de notas).
---

# compactar — compactación temporal + promoción a wiki

Hace *hierarchical temporal summarization*: bitácoras diarias → resumen semanal → resumen mensual,
y promueve hechos durables a `wiki/`. Uso: `/compactar semanal` o `/compactar mensual`.

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

## Modo mensual (`/compactar mensual [YYYY-MM]`)
1. Default: mes actual (`date +%Y-%m`).
2. Leé los resúmenes de `resumenes/semanal/` de ese mes.
3. Escribí `resumenes/mensual/<YYYY-MM>.md` con la misma estructura, a mayor altitud (tendencias del
   mes, decisiones estructurales, evolución de proyectos).

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

## Cierre (siempre)
- Actualizá `wiki/index.md` con las páginas nuevas/modificadas (una línea + descripción).
- Appendeá a `wiki/log.md`: fecha, qué se compactó, qué páginas tocó.
- No toques `raw/` ni reescribas las bitácoras (son el insumo, quedan como están).
