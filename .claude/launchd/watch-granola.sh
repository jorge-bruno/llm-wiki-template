#!/bin/zsh
# Disparado por el WatchPaths del LaunchAgent com.secondbrain.granola-transcript apenas
# Granola reescribe su cache. Corre el extractor (idempotente: dedupe por meeting_id),
# que descifra el cache local y materializa los transcripts nuevos en raw/granola/.
# launchd throttlea a ~1 corrida cada 15s, así que los writes frecuentes son inocuos.
set -euo pipefail

# Ruta del vault = dos niveles arriba de este script (.claude/launchd/ -> raíz del repo).
VAULT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$VAULT_DIR" || exit 1
echo "$(date '+%F %T') cache de Granola cambió → extrayendo transcripts"
exec .claude/scripts/granola-venv/bin/python .claude/scripts/granola_extract.py
