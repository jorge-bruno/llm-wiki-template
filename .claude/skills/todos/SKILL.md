---
name: todos
description: Genera y groomea los TODOs del second brain como notas en todos/ (que alimentan todos.base). Detecta accionables desde la bitácora reciente y el trabajo en progreso, deduplica contra Jira (PROJ) y contra los TODOs existentes. Usar para "generá los TODOs", "qué tengo pendiente", "armá la lista de tareas", o tras correr /bitacora.
---

# todos — generación y grooming de TODOs

Cada TODO es **una nota** en `todos/` (los Bases consultan notas, no checkboxes). Esta skill las
crea/actualiza desde el WIP y mantiene el board `todos.base` al día.

## Pasos

1. Reuní candidatos de accionables:
   - La sección "Pendientes detectados" de las bitácoras recientes (`bitacora/`).
   - Capturas recientes en `raw/` (compromisos en meetings, pedidos en Slack).
   - Opcional (si hay MCP de Atlassian): tickets PROJ abiertos del usuario vía
     `searchJiraIssuesUsingJql` con `project = PROJ AND assignee = currentUser() AND statusCategory != Done`.
2. **Dedupe** antes de crear:
   - Contra los TODOs existentes en `todos/` (mismo accionable / mismo proyecto+verbo).
   - Contra Jira: si el accionable ya es un ticket PROJ, **no** crees un TODO nuevo — referencialo
     (poné la key en `proyecto`) y marcá en el cuerpo que ya está en el board.
3. Para cada accionable nuevo, creá `todos/<slug-accion>.md`:
   ```markdown
   ---
   tags: [todo]
   estado: pendiente
   proyecto: <PROJ-NNN o nombre>
   due: <YYYY-MM-DD o vacío>
   origen: <raw/... o bitacora/...>
   created: <FECHA hoy>
   ---

   # <acción, verbo primero>

   <contexto breve: por qué, qué destraba, link a la fuente con [[wikilink]] o (fuente: ...)>
   ```
   El slug del archivo: `echo "<accion>" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-'`.
4. **Grooming**: si un TODO ya está hecho (aparece como entregado en una bitácora reciente o el
   ticket pasó a Done), actualizá su `estado: hecho` en vez de borrarlo (el board lo mueve a "Hechos").
5. Informá: cuántos TODOs nuevos, cuántos se saltearon por duplicado/Jira, cuántos pasaron a hecho.
   Recordá que `todos.base` muestra el board agrupado por proyecto/estado.

## Nota
- No transiciones ni crees tickets en Jira automáticamente. Los TODOs del vault son personales;
  si el usuario quiere subir alguno a PROJ, ofrecé la skill `create-ticket-jira`.
