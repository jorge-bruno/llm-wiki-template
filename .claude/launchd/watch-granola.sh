#!/bin/zsh
# Disparado por el WatchPaths del LaunchAgent com.secondbrain.granola-transcript apenas Granola
# reescribe su cache (cache-v6.json.enc). El write del cache es señal de "meeting nuevo/activo".
#
# Este watcher NO extrae nada del cache (Granola lo cifra y no lo desciframos): solo marca
# .postmeeting-pending para que el trigger post-meeting (run-postmeeting.sh) espere el settle del
# cache y dispare /refresh, que corre /capturar-granola (resúmenes vía MCP) cuando el meeting se
# asienta. launchd throttlea a ~1 corrida cada 15s, así que los writes frecuentes son inocuos.

# Ruta del vault = dos niveles arriba de este script (.claude/launchd/ -> raíz del repo).
VAULT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$VAULT_DIR" || exit 1
mkdir -p .claude/logs
touch .claude/logs/.postmeeting-pending
echo "$(date '+%F %T') cache de Granola cambió → .postmeeting-pending marcado (captura de resumen la hace /refresh vía MCP)"
