#!/bin/zsh
# Renderiza y carga los launchd agents del vault. Re-ejecutable / idempotente.
# Resuelve la ruta del vault y el binario de claude automáticamente (no hace falta editar nada).
# Tras editar cualquier .plist template del repo, volvé a correr este script para recargarlos.
#
# macOS-only (launchd). El cron es OPCIONAL: el pipeline también se corre a mano con
#   claude -p "/pipeline-diario"
set -euo pipefail

# Ruta del vault = dos niveles arriba de este script (.claude/launchd/ -> raíz del repo).
VAULT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$VAULT_DIR/.claude/launchd"
DEST="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
mkdir -p "$DEST" "$VAULT_DIR/.claude/logs"

# Binario de claude (CLI). Override: CLAUDE_BIN=/ruta/claude ./install.sh
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || echo "$HOME/.local/bin/claude")}"
if [[ ! -x "$CLAUDE_BIN" ]]; then
  echo "✗ No encontré el binario 'claude' ($CLAUDE_BIN). Instalá Claude Code o pasá CLAUDE_BIN=/ruta." >&2
  exit 1
fi
echo "vault:  $VAULT_DIR"
echo "claude: $CLAUDE_BIN"

for label in com.secondbrain.daily com.secondbrain.refresh com.secondbrain.postmeeting com.secondbrain.weekly com.secondbrain.monthly com.secondbrain.granola-transcript; do
  # Renderizo el template (placeholders -> valores reales) hacia ~/Library/LaunchAgents.
  sed -e "s#__VAULT_DIR__#$VAULT_DIR#g" \
      -e "s#__HOME__#$HOME#g" \
      -e "s#__CLAUDE_BIN__#$CLAUDE_BIN#g" \
      "$SRC/$label.plist" > "$DEST/$label.plist"
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  if launchctl bootstrap "$DOMAIN" "$DEST/$label.plist" 2>/dev/null; then
    echo "✓ cargado $label"
  else
    echo "✗ falló al cargar $label (revisá permisos / sintaxis del plist)"
  fi
done

echo "--- agentes activos ---"
launchctl list | grep -E 'secondbrain' || echo "(ninguno — revisá los errores de arriba)"
