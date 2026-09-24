# Clasificación de tier y política de retry MCP

Referencia compartida por `refresh`, `pipeline-diario`, `capturar-slack`, `capturar-calendar` y
`capturar-granola`. Es la fuente única: las 5 skills la referencian en vez de repetir la tabla (menos
tokens por corrida y una sola versión que mantener).

Precondición en todas: los tools `mcp__*` vienen **diferidos** en `claude -p` — cargalos primero con
`ToolSearch` usando `select:` y el nombre exacto del tool antes de sondear o capturar.

## Cómo clasificar el resultado (regla determinística — no lo decidas a ojo)

| Preflight | ToolSearch / llamada | Estado del tier |
|---|---|---|
| `connected: true` | anda | corré el tier |
| `connected: true` | el `select:` NO trae el schema | **`deferred`** — el conector está sano pero no quedó enumerado en esta sesión; el wrapper relanza una sesión nueva y ahí suele andar |
| `connected: true` | socket error / sin respuesta | reintentá (política de retry) y si no → **`deferred`** |
| `connected: false` | — | `skipped` (falta OAuth; no se arregla headless). En `pipeline-diario`: un intento de `authenticate` y si devuelve URL → confirma `skipped`. |

Pasa seguido que los 3 conectores de claude.ai (Slack/Calendar/Atlassian) no se enumeren juntos
mientras Granola sí: eso es enumeración fallida de la sesión, **no** "MCP no disponible". Un
`skipped` ahí descarta el día para nada (el conector conecta bien en la gran mayoría de las
sesiones). La enumeración fallida de los 3 conectores a la vez pasa en una fracción de las corridas
headless. Nunca declares un tier "no disponible" sin haber mirado el
preflight primero.

## Política de retry (aplicar en cada tier de red/MCP)

- **Comandos shell con red** (`git push`, extractores): envolvelos con
  `.claude/scripts/retry.sh --attempts 3 --base 2 --label "<qué> " -- <cmd...>`. Reintenta con
  backoff exponencial + jitter ante cualquier exit ≠ 0 (cubre 500s, socket errors y timeouts que el
  comando propaga como fallo).
- **Llamadas MCP** (las hace el agente, no el shell): ante **500 / socket error / stream idle
  timeout / "overloaded"**, reintentá hasta 3 veces con backoff `5s → 15s → 30s` (el backoff corto de
  1-2-4s no alcanzaba: cuando el proxy se cae, tarda más que eso en volver). Si tras los 3 sigue
  fallando y el preflight lo vio `connected` → marcá el tier **`deferred`** (no `skipped`) y seguí.
  **Ningún tier debe abortar el pipeline.**
