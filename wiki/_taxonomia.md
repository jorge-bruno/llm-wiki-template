---
tags: [meta]
---

# Taxonomía del vault

Vocabulario **controlado** para `tema`/tags. Usar SIEMPRE términos de esta lista (no inventar
variantes) para que la búsqueda del agente tenga recall alto. Si falta un tema, agregalo acá primero.

> Lo de abajo es un **ejemplo** orientado a Data Engineering. Adaptá los temas, áreas y equipos a tu
> propio dominio — es lo primero que conviene hacer tuyo.

## Temas (`tema:` en frontmatter)

**Plataforma de datos**
- `snowflake` · `dbt` · `airflow` · `terraform` · `aws`
- `data-modeling` · `ingesta` · `orquestacion` · `duckdb` · `dlt` · `ontologia`

**Gobernanza / seguridad**
- `rbac-seguridad` · `pii-gobernanza` · `finops-costos`

**Tracking / producto**
- `tracking` · `cdp-personalizacion`

**IA / tooling**
- `ia-agentes` (Claude, LLMs, agentes, skills) · `mcp` · `streamlit` · `productividad-tooling`

## Áreas (`area:` en biblioteca)

Agrupador de **alto nivel** para navegar la biblioteca (`biblioteca.base` → vista "Por área").
Un solo valor por nota (el emoji es parte del valor, para que aparezca como header en la vista
"Por área"). Mapeo desde `tema`:
- `🤖 ai-agentic` ← ia-agentes · mcp
- `🏗️ data-engineering` ← ingesta · orquestacion · dlt · duckdb · data-modeling · ontologia · dbt · airflow
- `❄️ snowflake` ← snowflake · finops-costos
- `☁️ cloud-infra` ← aws · terraform
- `🧰 tooling` ← productividad-tooling · streamlit

## Equipos (`equipo:` en personas)

Ejemplo: si trabajás en una org con varios squads, definí acá los valores válidos de `equipo:` para
las páginas de `wiki/personas/`. Ej:
- `mi-squad` — tu equipo directo.
- `plataforma` — equipo de plataforma.
- `externos` — contrapartes / clientes fuera de tu área.

## Campos de proyecto (`wiki/proyectos/`)
- `epic:` — la **épica de Jira** de la iniciativa (1 épica = 1 proyecto). Fuente de verdad del `estado`
  (la sincroniza `/compactar`). Ej. `epic: PROJ-187`.
- `ticket:` — *legacy*: ticket principal cuando el proyecto todavía no tiene épica. `/compactar` lo
  usa como fallback de `epic:`.
- `estado:` — `activo | pausado | cerrado`; lo deriva `/compactar` del status de la épica.

## Convenciones de naming
- Archivos: `lowercase-con-guiones.md`.
- Personas: `nombre-apellido.md` (ej. `ana-perez.md`).
- Sistemas/proyectos: nombre canónico en kebab-case (ej. `auto-table-creator.md`).
- **Aliases**: poné en el frontmatter (`aliases:`) las variantes y siglas con las que te referís a la
  entidad, para que `[[ATC]]`, `[[Auto Table Creator]]` y `[[auto-table-creator]]` resuelvan a la misma página.

## Tipos de recurso (biblioteca, `tipo:`)
`articulo` · `video` · `paper` · `thread` · `repo` · `curso` · `tip`
