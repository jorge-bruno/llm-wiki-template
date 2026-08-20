#!/bin/zsh
# Trigger event-driven: corre /refresh poco después de que TERMINA un meeting, para que los
# TODOs y la bitácora reflejen lo recién hablado sin esperar al próximo slot programado.
# Lo dispara un poller de launchd (com.secondbrain.postmeeting, StartInterval 120s).
#
# Solo actúa si:
#   (a) el watcher de Granola marcó trabajo nuevo (.postmeeting-pending), y
#   (b) el meeting "se asentó": el cache de Granola lleva >5 min sin reescribirse (terminó).
# Comparte el lock .refresh-lock con run-refresh.sh; NO usa el throttle de 90 min (un meeting
# nuevo debe procesarse aunque recién haya corrido un refresh programado).

# Ruta del vault = dos niveles arriba de este script (.claude/launchd/ -> raíz del repo).
VAULT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || echo "$HOME/.local/bin/claude")}"

cd "$VAULT_DIR" || exit 1
mkdir -p .claude/logs

PENDING=".claude/logs/.postmeeting-pending"
[ -f "$PENDING" ] || exit 0   # nada que procesar → salida barata

# Settle: si el cache se reescribió hace < 5 min, el meeting sigue activo → espero al próximo tick.
CACHE="$HOME/Library/Application Support/Granola/cache-v6.json.enc"
if [ -f "$CACHE" ]; then
  IDLE=$(( $(date +%s) - $(stat -f %m "$CACHE") ))
  if [ "$IDLE" -lt 300 ]; then
    echo "$(date '+%F %T') postmeeting: cache activo (${IDLE}s < 5min), espero settle"
    exit 0
  fi
fi

# Lock compartido con run-refresh.sh.
LOCK=".claude/logs/.refresh-lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  AGE=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$AGE" -lt 1200 ]; then
    echo "$(date '+%F %T') postmeeting: refresh en curso (lock ${AGE}s), reintento próximo tick"
    exit 0
  fi
  rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 0   # lock stale (>20min) → robar
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

echo "$(date '+%F %T') postmeeting: meeting asentado → corriendo /refresh"
"$CLAUDE_BIN" -p "/refresh"

# Si un tier quedó `deferred` (fuente sana que esta sesión no pudo usar porque su MCP no quedó
# enumerado), una sesión nueva suele resolverlo: `reopen` sale 0 sólo si había algo diferido.
if python3 .claude/scripts/pipeline_checkpoint.py reopen refresh 2>/dev/null >/dev/null; then
  echo "$(date '+%F %T') postmeeting: tier diferido, relanzo en sesión nueva"
  sleep 10
  "$CLAUDE_BIN" -p "/refresh"
fi

date +%s > .claude/logs/.refresh-last-run   # difiere el próximo refresh programado
rm -f "$PENDING"
