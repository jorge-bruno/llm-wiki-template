#!/usr/bin/env zsh
# gog_fetch.sh — baja un archivo de Google Suite a un archivo local usando el CLI `gog`.
#
# Uso:  gog_fetch.sh <google_url> [dest_basepath] [account_email]
#   dest_basepath: prefijo de salida (default /tmp/ingest-gog); se le agrega la extensión según el tipo.
#   account_email: cuenta de gog a usar (default: la cuenta default de gog).
#
# Imprime en stdout una sola línea:  "<ruta_archivo> <ya_markdown>"
#   ya_markdown = 1 para Google Docs (export md, listo para el vault), 0 para el resto (pasar por markitdown).
# Sale != 0 (con mensaje en stderr) si la URL no es de Google Suite o si gog falla.
set -euo pipefail

url="${1:-}"
dest="${2:-/tmp/ingest-gog}"
acct="${3:-}"
[[ -n "$url" ]] || { echo "uso: gog_fetch.sh <google_url> [dest_basepath] [account]" >&2; exit 2; }

acct_flag=()
[[ -n "$acct" ]] && acct_flag=(-a "$acct")

# fileId: patrón .../d/<ID>/...  o  ?id=<ID>
id="$(printf '%s' "$url" | sed -nE 's#.*/d/([a-zA-Z0-9_-]+).*#\1#p')"
[[ -z "$id" ]] && id="$(printf '%s' "$url" | sed -nE 's#.*[?&]id=([a-zA-Z0-9_-]+).*#\1#p')"
[[ -n "$id" ]] || { echo "no pude extraer el fileId de: $url" >&2; exit 1; }

# gog escribe su salida al archivo --out; mandamos su stdout a stderr para no ensuciar el contrato.
case "$url" in
  *docs.google.com/document*)
    out="${dest}.md";   gog docs export "$id" --format md --out "$out" "${acct_flag[@]}" >&2; echo "$out 1" ;;
  *docs.google.com/spreadsheets*)
    out="${dest}.csv";  gog download "$id" --format csv --out "$out" "${acct_flag[@]}" >&2; echo "$out 0" ;;
  *docs.google.com/presentation*)
    out="${dest}.pptx"; gog slides export "$id" --format pptx --out "$out" "${acct_flag[@]}" >&2; echo "$out 0" ;;
  *drive.google.com*)
    out="${dest}";      gog download "$id" --out "$out" "${acct_flag[@]}" >&2; echo "$out 0" ;;
  *)
    echo "URL no reconocida como Google Suite (Docs/Sheets/Slides/Drive): $url" >&2; exit 1 ;;
esac
