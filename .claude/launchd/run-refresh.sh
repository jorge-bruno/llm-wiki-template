#!/bin/zsh
# Mini-pipeline de refresh: capturar-granola/claude/slack/github + bitácora + todos + compactar diario
# + backup. Corre cada hora en punto (ver com.secondbrain.refresh.plist). La idempotencia de cada step
# protege contra duplicados. Comparte el lock .refresh-lock con el trigger post-meeting
# (run-postmeeting.sh) para no pisarse en git.

# Ruta del vault = dos niveles arriba de este script (.claude/launchd/ -> raíz del repo).
VAULT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || echo "$HOME/.local/bin/claude")}"

cd "$VAULT_DIR" || exit 1
mkdir -p .claude/logs

# Throttle de double-fire (ej. launchd dispara dos slots perdidos en el mismo wake):
# si ya corrió en los últimos 90 min, skip. (El trigger post-meeting NO usa este throttle:
# un meeting nuevo tiene que procesarse aunque recién haya corrido un refresh.)
LAST_RUN_FILE=".claude/logs/.refresh-last-run"
if [ -f "$LAST_RUN_FILE" ]; then
  DIFF=$(( $(date +%s) - $(cat "$LAST_RUN_FILE") ))
  if [ "$DIFF" -lt 5400 ]; then
    echo "$(date '+%F %T') refresh corrió hace ${DIFF}s (< 90 min), skip"
    exit 0
  fi
fi

# Lock compartido con run-postmeeting.sh: si hay un refresh en curso, salgo (no pisar git).
LOCK=".claude/logs/.refresh-lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  AGE=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$AGE" -lt 1200 ]; then
    echo "$(date '+%F %T') refresh: otra corrida en curso (lock ${AGE}s), skip"
    exit 0
  fi
  rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 0   # lock stale (>20min) → robar
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

date +%s > "$LAST_RUN_FILE"

# Dar tiempo a que levanten red y MCP tras wake/login.
sleep 20

# Gate de MCP: los conectores de claude.ai (Slack/Calendar/Atlassian) se listan consultando la cuenta, y
# tras un wake esa credencial puede no estar lista todavía. Si la sesión arranca en ese estado, no los
# enumera y esos tiers quedan diferidos de entrada. Esperamos hasta ~2 min a que sean visibles desde el
# shell; si no aparecen, corremos igual (best-effort: el tier quedará `deferred` y se reintenta).
for i in 1 2 3 4; do
  python3 .claude/scripts/pipeline_preflight.py --require-mcp >/dev/null 2>&1 && break
  echo "$(date '+%F %T') refresh: conectores MCP todavía no visibles, espero 30s (intento $i)"
  sleep 30
done

echo "$(date '+%F %T') corriendo /refresh"
# Reinvoke acotado: si la sesión muere a mitad (OOM, idle timeout, crash) o termina sin cerrar el
# checkpoint, reintentamos. El checkpoint (pipeline_checkpoint.py) persiste entre invocaciones, así
# que la 2da corrida RESUME desde el último tier completado en vez de reiniciar.
is_finished(){ python3 -c "import json,sys; sys.exit(0 if json.load(open('.claude/logs/.pipeline-checkpoint.refresh.json')).get('finished') else 1)" 2>/dev/null; }
# Un tier `deferred` es una fuente SANA (el preflight la vio ✔ Connected) que esta sesión no pudo usar
# porque su MCP no quedó enumerado al arrancar, o el proxy se cayó a mitad. La enumeración se decide por
# sesión, así que una sesión nueva suele resolverlo: `reopen` resetea ese tier + los downstream y sale 0
# sólo si había algo diferido (si no, no relanzamos nada).
reopen_if_deferred(){ out=$(python3 .claude/scripts/pipeline_checkpoint.py reopen refresh 2>/dev/null) || return 1; echo "$out"; }
attempt=1
while [ "$attempt" -le 3 ]; do
  "$CLAUDE_BIN" -p "/refresh"; rc=$?
  if [ "$rc" -eq 0 ] && is_finished; then
    if [ "$attempt" -le 2 ] && reopen_if_deferred; then
      echo "$(date '+%F %T') refresh: tier diferido (fuente sana, MCP no enumerado en la sesión), relanzo en sesión nueva (intento $attempt)"
      attempt=$((attempt+1)); sleep 10; continue
    fi
    break
  fi
  echo "$(date '+%F %T') refresh: corrida incompleta (rc=$rc), reinvoco para resumir (intento $attempt)"
  attempt=$((attempt+1)); sleep 10
done

# Procesado todo el raw/ acumulado → limpio el flag del post-meeting para no re-disparar.
rm -f .claude/logs/.postmeeting-pending
