---
name: compactar
description: Compacta la bitácora en resúmenes temporales (semanal/mensual), drena candidatos-gold pendientes y promueve el conocimiento durable a páginas de wiki. El modo diario (event-driven, sin resúmenes temporales — Interacciones + sync Jira + stage de candidatos) vive en la skill `compactar-diario`. Usar para "resumen semanal", "resumen del mes", "compactá la semana", "drená candidatos gold". Hierarchical temporal summarization (log compaction de notas).
---

# compactar — compactación temporal + promoción a wiki

Hace *hierarchical temporal summarization*: bitácoras diarias → resumen semanal → resumen mensual,
y promueve hechos durables a `wiki/`. Uso: `/compactar semanal` o `/compactar mensual`. El modo
diario event-driven (Interacciones + sync Jira + PRs recientes + stage de candidatos, invocado por
`/refresh` y `/pipeline-diario`) vive en la skill `compactar-diario` (`.claude/skills/compactar-diario/SKILL.md`).

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

> [!note] Interacciones / sync Jira / PRs recientes
> El detalle operativo de "Timeline de contacto por persona" (`## Interacciones`), "Sincronización
> de `estado` con Jira" y "PRs recientes por proyecto" vive en `compactar-diario/SKILL.md` — son
> mantenidos exclusivamente por el modo diario (event-driven), no por semanal/mensual/drenado.

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
