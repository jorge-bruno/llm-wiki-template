---
name: daily
description: Arma el status para tu daily standup (tu horario habitual de standup): qué se trabajó ayer, qué se va a hacer hoy y bloqueos. Consume la bitácora del día previo, los pendientes detectados y los TODOs abiertos; lo muestra en el chat y como paso final te lo manda por DM de Slack. Usar para "qué digo en la daily", "preparar la daily", "status del día".
---

# daily — status para la standup

Vista de consumo para tu daily standup. Lee los artefactos que el `pipeline-diario` ya generó
(capa silver) y los condensa en tres buckets: **ayer**, **hoy**, **bloqueos**. No escribe nada al
vault; como paso final te manda el resumen por DM de Slack para tenerlo en el teléfono. Correrla
antes de tu horario de standup.

> [!note] Política de retry MCP
> Las llamadas MCP de esta skill (envío a Slack, JQL de Atlassian) son frágiles a fallos
> transitorios. Ante **500 / socket error / stream idle timeout / "overloaded"**, reintentá hasta
> 3 veces con backoff `1s → 2s → 4s` antes de degradar. Ante error de **auth/desconexión** (no es
> transitorio) → no reintentes: degradá según el paso. Esto aplica al envío de Slack (paso 9) y a los
> chequeos de Jira (pasos 3d y la reconciliación).

## Pasos

1. **Fechas.**
   - `HOY=$(date +%F)`.
   - `AYER` = la bitácora más reciente con fecha estrictamente anterior a HOY. Obtenerla con:
     ```bash
     ls bitacora/*.md | sort | awk -F'/' '{print $NF}' | grep -v "^$(date +%F)" | tail -1 | sed 's/.md//'
     ```
     (Un lunes, "ayer" es el viernes — no asumir HOY-1.)
   - Convertí HOY al idioma/formato local para el header de output (ej: `2 de junio de 2026`).

2. **Ayer.** Leé `bitacora/<AYER>.md`.
   - La bitácora es la capa silver: verbosa, con varios bullets por iniciativa. Acá se **consolida,
     no se abstrae**: juntá los bullets de una misma iniciativa en **una sola línea** que diga qué se
     hizo, **conservando el detalle técnico que importa** (qué quedó andando, cómo se verificó, qué se
     mergeó/cerró). NO fragmentes en un bullet por hecho puntual; tampoco aguames a una abstracción
     vaga que pierda el qué concreto. Agrupá las keys de Jira (`PROJ-NNN`) de la iniciativa juntas.
   - Ejemplo. Bitácora (silver) — varios bullets de la misma iniciativa:
     > Se implementó y verificó el enforce de autenticación en el load balancer: request sin token →
     > 403, request con token → OK. PR mergeado. Ticket PROJ-144 creado…
     > Se revisó PROJ-214 (archivado de logs de errores a almacenamiento frío vía un pipeline batch) y
     > se finalizó.

     Daily (una línea, consolidada, sin perder el detalle):
     > Tracking de infraestructura: implementé y verifiqué el enforce de autenticación en el load
     > balancer (sin token → 403, con token → OK), PR mergeado; cerré también el archivado de logs de
     > errores a almacenamiento frío (PROJ-144, PROJ-214).
   - **Stripear** citas `(fuente: …)` y timestamps de Slack de cada bullet — no se dicen en
     la daily. **Conservar** las keys de Jira entre paréntesis (ej. `(PROJ-144)`).
   - Excluí la sección `### Agenda del día` de la bitácora (no es trabajo realizado).
   - **Degradación:** si `bitacora/<AYER>.md` no existe → avisá al usuario y ofrecé correr
     `/pipeline-diario` o `/bitacora`. Mientras tanto, armá best-effort leyendo
     `raw/claude/<AYER>.md`, `raw/granola/<AYER>*.md`, `raw/slack/<AYER>*.md` y los TODOs
     con `estado: hecho` y `created: <AYER>`.

3. **Hoy.** Construí la lista de compromisos del día en este orden de autoridad:

   a. **TODOs abiertos = fuente primaria.** Listar `todos/*.md` con `estado: pendiente | en-progreso`
      (`grep -l "estado: pendiente\|estado: en-progreso" todos/*.md`). Son la fuente con estado vivo:
      el pipeline los mantiene y ya están dedupeados contra Jira. Para cada uno, leé el título del
      archivo (la acción) y el campo `proyecto`. Agrupá por proyecto. Los `en-progreso` son lo que
      seguís hoy; los `pendiente`, lo que podés arrancar.

   b. **Pendientes detectados = solo lo que todavía no es TODO.** Leé la sección
      `## Pendientes detectados` de `bitacora/<AYER>.md` (si remite a un día anterior con "ver
      pendientes de …", seguí el puntero). Sumá **únicamente** los ítems que NO matchean ya un TODO
      abierto — son accionables sueltos sin materializar. No leas más bitácoras hacia atrás: lo que
      sigue vigente de días previos ya vive como TODO.

   c. **Reuniones de hoy** — leé `raw/calendar/<HOY>.md` si existe. Incluí las reuniones
      como compromiso del día (ej: `"<hora> Daily del equipo — [[ana-perez]], [[juan-gomez]]"`).
      Omitir las declinadas (aparecen al pie del calendar como "_(Excluido: ...)_").

   d. **Jira** *(opcional, best-effort)* — si el MCP de Atlassian está disponible, consultá:
      JQL `project = PROJ AND assignee = currentUser() AND statusCategory != Done` (reemplazá `PROJ`
      por el prefijo real de tu proyecto de Jira).
      Ante fallo transitorio, aplicá la *Política de retry MCP*; si tras los reintentos no responde o
      no está conectado → omitir en silencio, no abortar.

   **Reconciliación — sacá lo ya hecho (CRÍTICO).** Antes de emitir "Hoy", descartá todo candidato
   que ya esté terminado. La sección "Pendientes detectados" es un snapshot que no se reconcilia: un
   ítem detectado ayer puede haberse completado ayer mismo (o en una corrida de `/refresh`) y aun así
   figura ahí. Restá del bucket "Hoy":
   - **TODOs `estado: hecho`** — match por key de Jira (primario) y substring case-insensitive
     (fallback), **sin importar el `created`**. Si un candidato matchea un TODO hecho → no va a Hoy.
   - **Trabajo entregado en las bitácoras recientes** (`<AYER>` y la de hoy): bullets en pasado con
     verbos de cierre — "PR mergeado", "se finalizó", "se cerró", "ticket … completado/Done",
     "se implementó y verificó". Para el matching, usá **dos señales en paralelo**:
     a. **Key de Jira**: cualquier key mencionada en el candidato (campo `proyecto:` o cuerpo con
        regex `PROJ-\d+`) aparece en un bullet de cierre de la bitácora → ya está hecho.
        *Importante*: el ticket del TODO puede ser la épica (ej. PROJ-225) mientras el trabajo se
        cerró bajo un sub-ticket (ej. PROJ-237). Por eso también buscá las keys de los bullets de
        cierre de la bitácora hacia el candidato, no solo al revés.
     b. **Tokens semánticos**: tomá los 3-4 sustantivos/siglas más distintivos del nombre del TODO
        (ej. "Configurar permisos IAM roles staging cluster" → tokens: `IAM`, `staging`, `cluster`).
        Si ≥3 tokens aparecen en un mismo bullet de cierre de la bitácora → descartar; incluir nota
        interna "descartado por bitácora: <primer match>".
   - **Jira en vivo (best-effort, solo si MCP disponible):** juntá las keys de los candidatos
     que sobrevivieron los dos filtros anteriores y hacé una JQL `fields=["status"]`. Descartá de
     "Hoy" los que tengan `statusCategory.key == "done"`. Ante fallo transitorio, aplicá la *Política
     de retry MCP*; si tras los reintentos no responde → salteá en silencio.

   Esta resta es lo que evita listar como "Hoy" algo que ya se hizo ayer.

   **Dedupe entre fuentes:** key de Jira (primario) y substring case-insensitive (fallback). Un
   ítem que aparece en "pendientes" y también como TODO abierto → un solo bullet en el output.

4. **Bloqueos** *(solo si hay)*. Derivalos de los pendientes/TODOs que esperan a un tercero
   o dependencia externa: "esperando aprobación de PR", "pentest del equipo de seguridad pendiente",
   "doble check con el equipo dueño del servicio", etc. **Si no hay bloqueos, omitir la sección
   entera.**

5. **Etiquetar** cada bullet con su proyecto + key de Jira, mapeando nombre→key vía
   `wiki/proyectos/*.md` (campo `epic:` o `ticket:`). Ejemplo: si el pendiente dice
   "proyecto [[proyecto-ejemplo]]", leer `wiki/proyectos/proyecto-ejemplo.md`
   y tomar `epic: PROJ-144`.

6. **Output** — escribilo en el chat. **NO crear ni modificar ningún archivo.**
   ```markdown
   ## Daily — <HOY en formato local>

   **Ayer**
   - <Proyecto>: <qué se hizo, conciso> (PROJ-NNN)
   - <Proyecto>: <qué se hizo>

   **Hoy**
   - <Proyecto>: <qué se va a hacer> (PROJ-NNN)
   - <Proyecto>: <qué se va a hacer>

   **Bloqueos**
   - <dependencia o espera — omitir el bloque si no hay>
   ```
   Reglas:
   - **Una línea consolidada por iniciativa, con su detalle.** Juntá los deliverables de una misma
     iniciativa en un solo bullet, conservando el detalle técnico que dice qué se hizo concretamente
     (no lo aguames). No fragmentes en un bullet por hecho puntual ni lo bajes a una abstracción vaga.
   - Español rioplatense, primera persona ("implementé", "coordiné", "voy a diseñar"), conciso
     para hablar en voz alta: **1 línea por ítem**.
   - Sin citas de fuente, sin nombres de herramientas internas (agentes de IA, orquestadores, etc.),
     sin metadata, sin wikilinks en el output (se habla, no se linkea).
   - Etiquetar por proyecto; key de Jira entre paréntesis cuando aplique.
   - **Ayer** = lo entregado / **Hoy** = lo planeado / **Bloqueos** = lo que depende de otros.
   - **Sin tope de bullets.** Mostrá todas las iniciativas con trabajo (Ayer) o compromiso abierto
     (Hoy) — una línea consolidada por iniciativa. Ordená poniendo arriba los proyectos `activo` de
     `wiki/proyectos/`.

7. **Idempotencia.** La skill no toca el vault: no persiste, no modifica `raw/`, `bitacora/` ni
   `todos/`. Re-correrla regenera la misma vista. La **única** acción con efecto externo es el envío
   a Slack (paso 9): Slack no soporta upsert, así que cada corrida publica un DM nuevo en tu canal —
   re-correr `/daily` el mismo día deja varios mensajes. Es esperado.

8. **Cierre.**
   - Si al revisar los pendientes/TODOs detectás accionables nuevos que todavía no son TODO ni
     ticket, sugerí: "Hay N pendientes sin materializar — corré `/todos` para convertirlos en notas."
   - Si el check de Jira en vivo encontró candidatos ya Done que igual sobrevivieron los filtros
     locales (es decir, su TODO local todavía no está `hecho`), emití un aviso explícito:
     "⚠ N TODOs ya están Done en Jira (PROJ-X, PROJ-Y) pero siguen abiertos localmente — corré
     `/todos` para sincronizarlos."

9. **Enviar a Slack (paso final).** Mandá el resumen a tu propio DM de Slack para tenerlo en el
   teléfono durante la standup (tool MCP `slack_send_message`).
   - **Canal:** tu propio `user_id` como `channel_id` (self-DM). El MCP de Slack expone el user_id
     del usuario logueado — usá ese valor tal como lo devuelve el MCP, no lo hardcodees.
   - **Contenido:** el output del paso 6 tal cual (los tres buckets). NO incluyas los avisos del
     Cierre (paso 8) — esos quedan solo en el chat. Es markdown estándar y el MCP lo renderiza bien
     (header `##`, negritas `**…**`, código con backticks); mantené las keys de Jira.
   - **Directo, no draft:** el usuario ya revisó el resumen en el chat (paso 6). Devolvé el link del
     mensaje en el chat.
   - **Retry + degradación:** si el envío falla por un error transitorio (500/socket/idle/overloaded),
     reintentá con el backoff de la *Política de retry MCP* (1s → 2s → 4s). Si tras los reintentos
     sigue fallando, o el MCP no está conectado (error de auth) → avisá en el chat ("No pude mandar el
     resumen a Slack: <motivo>") y dejá el output del chat como fallback. No abortes.

## Nota

Correr **después** del `pipeline-diario` (que genera la bitácora y los TODOs). Idealmente unos
minutos antes de tu daily standup. Calendar y Jira son best-effort y degradan con gracia.
La bitácora de ayer es la fuente principal; sin ella, el output pierde fidelidad.
