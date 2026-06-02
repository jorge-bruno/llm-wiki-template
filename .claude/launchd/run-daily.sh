#!/bin/zsh
# Corre /pipeline-diario UNA sola vez por día, sin importar si el disparador fue
# RunAtLoad (encender / iniciar sesión) o StartCalendarInterval (horario / despertar).
# El candado por fecha evita corridas dobles cuando ambos triggers caen el mismo día.
set -euo pipefail

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
find .claude/logs -maxdepth 1 -type d -name '.daily-*' ! -name ".daily-$TODAY" -exec rm -rf {} + 2>/dev/null || true

# Doy tiempo a que levanten red / MCP después del login o el wake.
sleep 60

echo "$(date '+%F %T') corriendo /pipeline-diario"
exec "$CLAUDE_BIN" -p "/pipeline-diario"
