#!/bin/zsh
# Corre /pipeline-diario UNA sola vez por día, sin importar si el disparador fue
# RunAtLoad (encender / iniciar sesión) o StartCalendarInterval (horario / despertar).
# El candado por fecha evita corridas dobles cuando ambos triggers caen el mismo día.

# Ruta del vault = dos niveles arriba de este script (.claude/launchd/ -> raíz del repo).
VAULT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || echo "$HOME/.local/bin/claude")}"

cd "$VAULT_DIR" || exit 1
mkdir -p .claude/logs
TODAY=$(date +%F)
LOCKDIR=".claude/logs/.daily-$TODAY"

# Candado atómico por día: si el directorio ya existe, otra corrida de hoy ganó → salgo.
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "$(date '+%F %T') ya corrió hoy ($TODAY), skip"
  exit 0
fi

# Limpio candados de días anteriores.
find .claude/logs -maxdepth 1 -type d -name '.daily-*' ! -name ".daily-$TODAY" -exec rm -rf {} + 2>/dev/null

# Doy tiempo a que levanten red / MCP después del login o el wake.
sleep 60

# Gate de MCP: los conectores de claude.ai (Slack/Calendar/Atlassian) se listan consultando la cuenta, y
# tras el login esa credencial puede no estar lista todavía. Si la sesión arranca en ese estado, no los
# enumera y esos tiers quedan diferidos de entrada. Esperamos hasta ~2 min a que sean visibles desde el
# shell; si no aparecen, corremos igual (best-effort: el tier quedará `deferred` y se reintenta).
for i in 1 2 3 4; do
  python3 .claude/scripts/pipeline_preflight.py --require-mcp >/dev/null 2>&1 && break
  echo "$(date '+%F %T') pipeline-diario: conectores MCP todavía no visibles, espero 30s (intento $i)"
  sleep 30
done

echo "$(date '+%F %T') corriendo /pipeline-diario"
# Reinvoke acotado: si la sesión muere a mitad o termina sin cerrar el checkpoint, reintentamos;
# el checkpoint persiste entre invocaciones → la 2da corrida resume desde el último tier completado.
is_finished(){ python3 -c "import json,sys; sys.exit(0 if json.load(open('.claude/logs/.pipeline-checkpoint.pipeline-diario.json')).get('finished') else 1)" 2>/dev/null; }
# Un tier `deferred` es una fuente SANA (el preflight la vio ✔ Connected) que esta sesión no pudo usar
# porque su MCP no quedó enumerado al arrancar, o el proxy se cayó a mitad. La enumeración se decide por
# sesión → una sesión nueva suele resolverlo. `reopen` resetea ese tier + los downstream y sale 0 sólo si
# había algo diferido.
reopen_if_deferred(){ out=$(python3 .claude/scripts/pipeline_checkpoint.py reopen pipeline-diario 2>/dev/null) || return 1; echo "$out"; }
attempt=1; RC=1
while [ "$attempt" -le 3 ]; do
  "$CLAUDE_BIN" -p "/pipeline-diario"; RC=$?
  if [ "$RC" -eq 0 ] && is_finished; then
    if [ "$attempt" -le 2 ] && reopen_if_deferred; then
      echo "$(date '+%F %T') pipeline-diario: tier diferido (fuente sana, MCP no enumerado en la sesión), relanzo en sesión nueva (intento $attempt)"
      attempt=$((attempt+1)); sleep 15; continue
    fi
    break
  fi
  echo "$(date '+%F %T') pipeline-diario: corrida incompleta (rc=$RC), reinvoco para resumir (intento $attempt)"
  attempt=$((attempt+1)); sleep 15
done
date +%s > ".claude/logs/.daily-done-$TODAY"
exit $RC
