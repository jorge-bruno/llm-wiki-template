---
tags: [decision]
tema: [ingesta, aws, snowflake]
last_updated: 2026-01-15
---

# Arquitectura de ingesta: event-driven sobre pull-based

**Resumen**: Para el [[pipeline-ingesta]] se decidió un enfoque event-driven (cola → consumer →
warehouse) por sobre polling periódico. (Ejemplo sintético.)

**Fuentes**: raw/granola/2026-01-15-kickoff-ingesta.md (PROJ-101)

---

**Contexto**: arrancamos el diseño del pipeline de ingesta hacia [[snowflake]].

**Decisión**: event-driven en vez de pull-based, por menor latencia y mejor manejo de backpressure.

**Por qué (el porqué es lo caro de perder)**: el volumen es bursty; el polling desperdiciaría
recursos en ventanas vacías y agregaría latencia. Pendiente de validación con un POC ([[ana-perez]]).

## Páginas relacionadas
- [[pipeline-ingesta]]
- [[snowflake]]
