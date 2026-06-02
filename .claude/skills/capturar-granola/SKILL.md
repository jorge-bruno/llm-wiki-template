---
name: capturar-granola
description: Captura transcripts verbatim de meetings de Granola al second brain (raw/granola/), descifrando el cache local de la app (sin MCP). Usar para ingestar reuniones recientes o en el pipeline diario. CRÍTICO porque el cache de Granola es rotativo y free borra las notas a los ~7 días — esta captura es lo que las preserva. Idempotente por meeting_id.
---

# capturar-granola — ingesta de meetings de Granola (cache local)

Captura los transcripts **verbatim** de Granola hacia `raw/granola/`. **Tier 1 / crítico.**

Granola guarda el transcript completo de cada meeting reciente en su cache local cifrado
(`~/Library/Application Support/Granola/cache-v6.json.enc`, AES-256-GCM). El MCP remoto gatea el
transcript por tier pago, así que **NO lo usamos**: extraemos del cache local con
`.claude/scripts/granola_extract.py`, que lee la llave del Keychain, descifra el cache y materializa
cada meeting nuevo. El docstring del script documenta el esquema de cifrado (DEK del Keychain → AES-256-GCM).

> [!important] El cache es un working-set ROTATIVO
> Solo retiene meetings recientes; los viejos se evictan. Por eso un **LaunchAgent**
> (`com.secondbrain.granola-transcript`) corre el extractor en cada escritura del cache (`WatchPaths`), de
> modo que la preservación es continua y no depende de esta corrida. Esta skill es el disparo
> manual/diario + la promoción a wiki.

## Pasos

1. Corré el extractor (captura todos los meetings nuevos, dedupe por `meeting_id` contra `raw/granola/`).
   Usá **el venv dedicado** (el `python3` del sistema NO tiene `cryptography`; el watcher launchd usa este mismo venv):
   ```bash
   .claude/scripts/granola-venv/bin/python .claude/scripts/granola_extract.py
   ```
   Devuelve JSON con `results[]`: cada item trae `status` (`captured` / `skipped` / `overwritten`),
   `archivo`, `titulo`, `n_segments`. Para ver qué hay en el cache sin escribir: `--list`. Para
   (re)capturar uno puntual y sobrescribir: pasá el `<meeting_id>`.
2. Informá qué meetings nuevos se capturaron y cuáles se saltearon por estar ya guardados.
3. Para los **nuevos**, leé el `raw/granola/<archivo>.md` (el transcript verbatim) y ofrecé promover
   al wiki personas/proyectos/sistemas/decisiones que aparezcan, siguiendo el flujo de ingesta del
   `CLAUDE.md`. **NO toques `raw/` después de escribirlo** (salvo recaptura explícita por meeting_id).

## Notas
- **No hay summary de Granola**: ese resumen lo genera el server y no está local. No importa — `/bitacora`
  sintetiza el resumen del día desde el transcript en `raw/`. La captura es solo el transcript verbatim.
- **Degradación con gracia**: si Granola no está corriendo, el cache no existe, o el Keychain está
  bloqueado, el script devuelve `{"error": ...}` y sale con código ≠ 0. Informalo y terminá sin romper
  el pipeline (igual el watcher captura cuando la app vuelva a escribir el cache).
- **Requisito de automatización**: el script lee la llave del Keychain con `security`; hace falta un
  "Always Allow" único sobre el item `Granola Safe Storage`. Los LaunchAgents corren en tu sesión, así
  que el keychain está desbloqueado y la lectura es no-interactiva.
- Etiquetas del transcript: `Mic` = micrófono local (vos), `Sistema` = audio remoto. Granola free no
  diariza (no hay nombres por hablante).
