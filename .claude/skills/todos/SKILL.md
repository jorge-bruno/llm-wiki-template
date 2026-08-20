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

   **Atribución de owner — un TODO se crea SOLO si la acción es del usuario.** En meetings de
   equipo y threads de Slack la mayoría de los pendientes son de OTRA persona; capturarlos todos
   llena el board de tareas ajenas. **Atribuí por el SUJETO de la acción en la fuente, no por el
   verbo del título:** un título en infinitivo neutro ("Revisar perfiles de sourcing…") suena tuyo
   aunque la fuente deje claro que el ejecutor es otro. Leé la fuente —quién tiene la pelota— antes
   de decidir. Para cada candidato decidí:
   - **Ajeno → NO crear.** La fuente ata la ejecución a otra persona. La bitácora suele marcarlo
     explícito: `[[juan-gomez]] lo toma`, `… valida y notifica`, `[[ana-perez]] corre la migración`,
     o es trabajo de otro squad. Verbos de ejecución (`toma`, `levanta`, `resuelve`, `corre`,
     `ejecuta`, `aplica`, `valida y notifica`) atados a un nombre que **no** es el usuario →
     descartar; loggear "descartado por owner ajeno: <persona>".
   - **Waiting-for (monitoreo pasivo de acción ajena) → NO crear.** El accionable es *vigilar* que
     otro haga su parte, no ejecutar vos: "hacer seguimiento de cuándo [[X]] comparte/responde",
     "participar si corresponde", "estar atento a que salga Y", "ver qué dice X". No hay entregable
     tuyo, solo espera; tu rol es condicional (`si corresponde`, `si aplica`) o de mera observación.
     Distinto de coordinar (abajo), que SÍ tiene un entregable tuyo (mandar, agendar, pedir). Ajeno
     pasivo → descartar; loggear "descartado por waiting-for: <persona/tema>".
   - **Tuyo aunque la implementación sea de otro → crear.** El verbo del usuario ES la tarea:
     `coordinar con X`, `verificar que la skill de X invoque…`, `revisar/aprobar PR de X`,
     `pasarle/comunicarle a X`. La acción de coordinación/review/comunicación es del usuario.
   - **Compartida ("el usuario y X juntos", "el usuario y ana-perez graban") → crear con
     `tags: [todo, compartida]`** y dejá en el cuerpo cuál es tu parte y con quién.
   - **Cruce con Jira (si el candidato mapea a un PROJ):** si el ticket tiene `assignee != <el
     usuario>`, tratalo como ajeno **salvo** que el accionable sea una acción de coordinación/review
     tuya (regla anterior). El status `statusCategory != Done` solo dice que sigue abierto, no que
     sea tuyo.

   **Filtro de esfuerzo — un accionable de <5 min NO merece TODO.** Si el "done" se alcanza con
   **una sola acción atómica**, es demasiado chico para documentar: se resuelve en el flujo normal
   de trabajo y solo genera churn (crear → cerrar). **No lo crees.**

   **Test operativo** (aplicalo antes de crear, siempre): *¿el enunciado ya contiene la instrucción
   completa de qué hacer, y ejecutarla es un solo paso?* Si sí → descartar. Un TODO existe para
   recordar trabajo que hay que **planificar**, no para recordar un gesto que ya sabés hacer.

   Las tres familias que caen (con ejemplos ilustrativos):
   - **micro-verificación** — mirar un estado que ya está definido y esperar a que cambie solo:
     "confirmar que entre una fila real por el pipe", "confirmar si un CI/CD tuvo una caída". Se
     resuelve con una query o un vistazo. Si el chequeo **falla**, el trabajo que se destape ahí sí
     amerita TODO — en ese momento, no antes.
   - **micro-comunicación** — un mensaje suelto: "preguntarle a X qué contenía el adjunto",
     "consultarle a X por la fecha de sistema". Se manda ahora, no se agenda.
   - **micro-PR** — aprobar / mergear / revisar / verificar un **PR puntual**.

   **Excepciones (sí se crean):**
   - Si la micro-acción es el *entregable* de una tarea sustantiva (una feature, una migración), el
     TODO es **esa tarea más grande**, no el paso chico.
   - Un accionable que solo se **mencionó** (Slack, meeting) y no tiene ningún trabajo en curso
     detrás sí va, aunque suene chico de enunciar: "evaluar armar una guía de cómo construir
     ingestas", "implementar error budget en las alertas". Enunciarlos toma un renglón; hacerlos,
     varias sesiones. El corte es el **esfuerzo de ejecución**, no el largo del título.

   Loggear "descartado por esfuerzo: <micro-verificación|micro-comunicación|micro-PR>".
2. **Dedupe** antes de crear (tres filtros en orden):
   - Contra los TODOs existentes en `todos/` (mismo accionable / mismo proyecto+verbo). Esto
     **incluye los `estado: descartado`**: son *tombstones* — accionables que ya rechazaste (owner
     ajeno, waiting-for, no-va). Si un candidato matchea un descartado → **no lo recrees**; loggear
     "no recreado por tombstone: <slug>". Sin esto, un ajeno que descartás reaparece mientras su
     `origen` siga en la ventana de captura.
   - Contra Jira: si el accionable ya es un ticket PROJ, **no** crees un TODO nuevo — referencialo
     (poné la key en `proyecto`) y marcá en el cuerpo que ya está en el board.
   - **Contra bitácoras recientes** (ventana: últimas 3 entradas de `bitacora/`, leelas con `ls bitacora/*.md | sort | tail -3`):
     para cada candidato, verificar si ya aparece como **entregado**. Dos señales de cierre a buscar
     en los bullets de la bitácora: verbos de cierre (`mergeado`, `completó`, `finalizó`, `cerró`,
     `implementó y verificó`, `Done`, `completado`) combinados con alguno de estos matches:
     a. **Key Jira match**: la key del candidato (del campo `proyecto:` o del cuerpo con regex
        `PROJ-\d+`) coincide con una key en un bullet de cierre → descartar, no crear.
     b. **Tokens semánticos**: tomá los 3-4 sustantivos/siglas más distintivos del accionable (ej.
        para "Configurar permisos IAM para el servicio de reportes" → tokens: `IAM`, `permisos`,
        `reportes`). Si ≥3 de esos tokens aparecen en un mismo bullet de cierre → descartar, no
        crear; loggear "descartado por bitácora: <bullet>".
     **Por qué importa**: un TODO puede etiquetarse con la épica contenedora (ej. PROJ-225) mientras
     el trabajo se cerró bajo un sub-ticket (ej. PROJ-237). Sin este check, el pipeline crea TODOs
     stale para trabajo ya entregado.
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
4. **Grooming de cierre — evidencia de entrega, señal DURA, cero falsos cierres.**
   El bug clásico: un TODO es un **sub-paso atómico**, pero el ticket Jira que lo contiene es una
   **épica/feature** que sigue abierta meses. Cerrar solo cuando el ticket pasa a `Done` deja el
   sub-paso colgado para siempre. Por eso el cierre se decide por **evidencia de entrega**, aunque
   el ticket siga abierto.

   **Clasificá cada TODO por peso** (por la forma del accionable, sin campo nuevo) — define qué vías
   de cierre aplican. Las micro-acciones **ya no se crean** (filtro de esfuerzo del paso 1): esta
   clasificación existe para **drenar los legacy** que quedaron en el board:
   - **Micro-acción** = su "done" deja rastro en una fuente externa consultable:
     - *micro-PR*: aprobar / mergear / verificar / revisar **PR #N** → rastro en GitHub (vía c).
     - *micro-comunicación*: responder / avisar / confirmar / coordinar a alguien, con origen
       `raw/slack/` → rastro en Slack (vía d).
   - **Sustantiva** = migrar, implementar, definir, evaluar, diseñar, investigar. Su "done" es un
     entregable real → **solo** cierra por bitácora (a) o Jira (b). **Nunca** por señal blanda: que
     en Slack digan "buenísimo" no cierra una migración a prod.

   **a. Grooming por bitácora (corre SIEMPRE, sobre todos los TODOs con `estado != hecho`).**
   - Ventana: leé las bitácoras desde el `created` del TODO hasta hoy (no solo las últimas 3). En
     la práctica: `ls bitacora/*.md | sort` y tomá las de fecha ≥ `created`. Acotá a los últimos
     **14 días** como tope para no explotar tokens.
   - Para cada TODO, buscá en esas bitácoras el mismo accionable como **entregado**: verbos de
     cierre (`mergeado`, `completó`, `finalizó`, `cerró`, `implementó y verificó`, `Done`,
     `aplicado`, `resuelto`) + match por **key Jira** o por **≥3 tokens semánticos** distintivos
     (mismo criterio que el dedupe del paso 2). Si matchea → setear `estado: hecho` y appendear:
     ```
     ## Cierre <YYYY-MM-DD> — entregado según bitácora <bitacora/YYYY-MM-DD.md>: "<bullet>"
     ```
   - Esto cubre por igual TODOs **con y sin** key Jira (los sin key —temas internos sin ticket—
     solo tienen esta vía).

   **b. Sync contra Jira (Tier 2, best-effort, complementa lo anterior).**
   - Juntá las keys Jira de los TODOs aún `estado != hecho` (campo `proyecto:` formato `PROJ-NNN`, o
     fallback regex `PROJ-\d+` en el cuerpo). Una sola JQL: `project = PROJ AND key in (…)` con
     `fields=["status"]`. Mismo patrón que `/compactar` en "Sincronización de `estado` con Jira".
   - Ticket en `statusCategory.key == "done"` → setear `estado: hecho` + nota de cierre
     `## Cierre <YYYY-MM-DD> — <PROJ-NNN> pasó a <status> en Jira`.
   - **Ticket abierto NO implica TODO abierto**: si la épica sigue `En curso` pero el grooming por
     bitácora (a) ya cerró el sub-paso, respetá el `hecho` — no lo reabras.
   - **Degrada en silencio**: si el MCP de Atlassian no está → salteá este sub-paso (la vía (a)
     sigue siendo el fallback).

   **c. Cierre por GitHub (micro-PR, determinística).** Los micro-PR ya no se crean (filtro de
   esfuerzo del paso 1); esta vía drena los **legacy** y cualquiera que se cuele. Para TODOs
   micro-PR (título/cuerpo con `PR #N` o "aprobar/mergear/verificar PR"):
   - Extraé el número `N` y el repo (del texto, o iterando los repos de
     `.claude/config/github-repos.txt`). Corré **en vivo**:
     ```
     gh pr view <N> --repo <owner/repo> --json state,mergedAt,title
     ```
   - `state == "MERGED"` → `estado: hecho` + `## Cierre <YYYY-MM-DD> — PR #<N> merged <mergedAt> (GitHub)`.
   - `state == "CLOSED"` (sin merge) → el PR no va: listalo como candidato a descartar (paso 6);
     **no** lo auto-cierres ni descartes.
   - `state == "OPEN"` → sigue pendiente, no lo toques.
   - **Determinística**: no depende de `raw/github/`; usa el estado actual del PR. Degrada en
     silencio si `gh` no está autenticado.

   **d. Cierre por Slack (micro-comunicación, semántica, umbral ALTO).** Para TODOs micro-comunicación
   con origen `raw/slack/`:
   - En Slack casi nunca aparece "hecho/mergeado" literal → **inferí de la conversación sobre el
     tema, no por keyword**. Tomá los 3-4 tokens distintivos del accionable, grepealos en
     `raw/slack/*.md` con fecha ≥ `created`, leé los hilos que matchean y juzgá si el tema se
     **resolvió** (confirmación explícita, la contraparte agradece/cierra, o el pedido no se
     re-pregunta y deriva a otra cosa).
   - Evidencia **inequívoca** → `estado: hecho` + `## Cierre <YYYY-MM-DD> — resuelto en Slack (ts: <ts>): "<resumen>"`.
   - **Ambiguo → NO cierres**; listalo como candidato (paso 6). El umbral alto es lo que garantiza
     cero falsos cierres.
   - Corre sobre `raw/slack/` en disco (bronze), no sobre el MCP en vivo (que no anda headless).

   **e. Caducidad / revisión manual.** Un TODO con `estado != hecho`, `created` de hace **>14 días**
   y sin evidencia de cierre → **no** lo auto-cierres, pero listalo en el informe (paso 6) bajo
   "Candidatos a revisar (pendientes >14 días sin actividad)" para que el usuario decida.

   **f. Revisión retroactiva de owner y esfuerzo.** Repasá los abiertos existentes con las reglas
   del paso 1: la de **owner** (waiting-for / ajeno) y la de **esfuerzo** (micro-verificación /
   micro-comunicación / micro-PR que se colaron antes del filtro). Si alguno cae → **no** lo
   auto-descartes; listalo en el informe (paso 6) bajo "Candidatos a descartar", con el motivo
   (owner ajeno · waiting-for · esfuerzo), para que lo arrastres a `descartado` en el kanban. El
   descarte es tuyo, no del pipeline.

   **Idempotente**: un TODO ya `hecho` **o `descartado`** no se re-toca (ambos son terminales); la
   nota de cierre no se duplica. Un `descartado` **nunca** se reabre ni se pasa a `hecho`.
5. **Regenerá el kanban HTML** corriendo:
   ```
   python3 .claude/scripts/build_kanban_html.py
   ```
   Este script lee todos `todos/*.md`, parsea el frontmatter y genera `kanban.html`
   (auto-contenido, con drag & drop que escribe el `estado:` de vuelta al `.md` vía
   node-integration de Electron). `kanban.html` no se versiona (`.gitignore`).
6. Informá: cuántos TODOs nuevos; cuántos se descartaron al crear (**por owner ajeno**, **por
   waiting-for** y **por esfuerzo**, con la persona/tema o la familia); cuántos no se recrearon
   **por tombstone**; cuántos se saltearon por duplicado/Jira; cuántos pasaron a `hecho` (y de esos,
   cuántos por bitácora vs. por sync Jira); la lista de **"Candidatos a revisar (pendientes >14 días
   sin actividad)"**; y la de **"Candidatos a descartar"** con su motivo (paso 4f). Tanto
   `todos.base` como `kanban.html` reflejan el estado actualizado.

## Estados y el tombstone `descartado`
- Estados: `pendiente` · `en-progreso` · `hecho` · `descartado`. `hecho` y `descartado` son **terminales**.
- `descartado` = accionable rechazado (owner ajeno, waiting-for, o simplemente no-va). Funciona de
  *tombstone*: el dedupe (paso 2) no lo recrea mientras el archivo exista. Lo marcás **vos**
  arrastrando la card a la columna "descartado" del kanban (o poniendo `estado: descartado` a mano).
  El pipeline **no** auto-descarta — solo sugiere candidatos (paso 4d).
- Tanto `todos.base` (vista Abiertos) como el kanban ocultan los terminales de la vista activa.
- El tombstone solo necesita vivir mientras su `origen` siga en la ventana de captura; `/limpiar-todos`
  borra los `descartado` viejos igual que los `hecho`.

## Nota
- No transiciones ni crees tickets en Jira automáticamente. Los TODOs del vault son personales;
  si el usuario quiere subir alguno a PROJ, ofrecé tu skill de crear tickets (si tenés una).
