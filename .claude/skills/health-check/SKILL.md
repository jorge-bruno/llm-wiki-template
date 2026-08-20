---
name: health-check
description: Diagnóstico rápido del estado del second brain — LaunchAgents, última corrida del pipeline, meetings de Granola sin procesar en bitácora, TODOs hechos sin archivar, candidatos-gold pendientes. Usar antes de una reunión, después de una ausencia larga, o cuando sospechés que el pipeline falló.
---

# health-check — diagnóstico del segundo brain

Reporte en ~10–15 líneas del estado operativo del vault. Read-only, no escribe nada.

## Pasos

### 1. LaunchAgents — ¿están cargados?

```bash
launchctl list | grep "com.secondbrain"
```

Para cada plist relevante, reportá si aparece con PID (corriendo) o sin PID (cargado pero inactivo),
o si no aparece (no cargado). Los plists del vault:
- `com.secondbrain.daily` — pipeline diario (mañana)
- `com.secondbrain.weekly` — compactación semanal
- `com.secondbrain.monthly` — compactación mensual
- `com.secondbrain.granola-transcript` — watcher del cache de Granola (WatchPaths sobre el cache
  cifrado local); solo marca `.postmeeting-pending`
- `com.secondbrain.postmeeting` — poller post-meeting que dispara `/refresh` cuando el meeting se
  asienta

### 2. Última corrida del pipeline

Buscá el raw/claude/ más reciente para estimar cuándo fue la última captura:
```bash
ls -t raw/claude/*.md | head -3
```
También mirá el último commit del vault:
```bash
git log --oneline -5
```
Reportá: fecha del último `raw/claude/` + fecha del último commit. Si el `raw/claude/` más reciente
tiene más de 25 horas, el pipeline no corrió ayer.

### 3. Meetings de Granola del día sin reflejar en bitácora

```bash
ls raw/granola/$(date +%F)*.md 2>/dev/null
grep -l "$(date +%F)" bitacora/*.md
```

Para cada meeting de hoy en `raw/granola/`, chequeá si su contenido está reflejado en
`bitacora/$(date +%F).md` (heurística: si el archivo de bitácora existe y tiene más de 5 líneas
más allá del frontmatter, asumí que fue procesado; si tiene solo "Agenda" → pendiente).

### 4. TODOs con `estado: hecho` (candidatos a limpiar)

```bash
grep -l "estado: hecho" todos/*.md | wc -l
grep -l "estado: hecho" todos/*.md
```

Reportá cuántos hay y sus nombres. Si son más de 5, el board `todos.base` está contaminado —
sugerí correr `/limpiar-todos` cuando esté disponible, o manualmente borrar los más viejos.

### 5. candidatos-gold/ pendientes de revisión

```bash
ls candidatos-gold/*.md 2>/dev/null | grep -v ".gitkeep" | wc -l
grep -l "estado: pendiente" candidatos-gold/*.md 2>/dev/null
```

Reportá cuántos hay pendientes. Si hay candidatos, mencioná qué tipo son (persona/sistema/decisión).

### 6. Bitácoras de los últimos 3 días — ¿existen?

```bash
for i in 0 1 2; do
  d=$(date -v-${i}d +%F 2>/dev/null || date -d "-${i} days" +%F)
  [ -f "bitacora/$d.md" ] && echo "✓ $d" || echo "✗ $d (falta)"
done
```

Si falta alguna → sugerí correr `/bitacora`.

## Formato de output

```
# Health check — <FECHA HOY>

## Pipeline
- LaunchAgents: daily ✓ | weekly ✓ | monthly ✓ | granola-watcher ✓
- Última corrida: raw/claude/<FECHA>.md (<N>h atrás) | último commit: <mensaje>

## Granola hoy
- <N> meetings capturados: <lista>
- Bitácora <FECHA>: procesada ✓ / incompleta ⚠️ / falta ✗

## TODOs hechos sin archivar: <N>
  - <lista de nombres>

## candidatos-gold pendientes: <N>
  - <lista si hay>

## Bitácoras
- <FECHA-0>: ✓ / ✗
- <FECHA-1>: ✓ / ✗
- <FECHA-2>: ✓ / ✗
```

Si todo está OK, terminá con una línea: `Todo en orden ✓`. Si hay algo roto o pendiente,
listá las acciones sugeridas al final (máx. 3 bullets).
