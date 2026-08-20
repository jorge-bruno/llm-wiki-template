#!/bin/zsh
# retry.sh — reintenta un comando con backoff exponencial + jitter.
#
# Uso:
#   retry.sh [--attempts N] [--base S] [--max S] [--label TXT] -- <cmd> [args...]
#
#   --attempts N   intentos totales (default 3)
#   --base S       backoff base en segundos (default 2): el intento k espera base*2^(k-1)
#   --max S        tope del backoff por intento (default 60)
#   --label TXT    etiqueta para los logs (default: el comando)
#
# Reintenta ante CUALQUIER exit ≠ 0 (cubre 500s, socket errors y timeouts que el comando
# propaga como fallo). Para llamadas MCP —que las hace el agente, no el shell— la política de
# retry vive en la SKILL del pipeline.
#
# Sale con 0 al primer éxito, o con el último rc tras agotar los intentos.

emulate -L zsh

attempts=3
base=2
maxd=60
label=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --attempts) attempts="$2"; shift 2 ;;
    --base)     base="$2";     shift 2 ;;
    --max)      maxd="$2";     shift 2 ;;
    --label)    label="$2";    shift 2 ;;
    --)         shift; break ;;
    *)          break ;;
  esac
done

if [[ $# -eq 0 ]]; then
  echo "retry.sh: falta el comando (usá: retry.sh [opts] -- cmd args)" >&2
  exit 2
fi
[[ -n "$label" ]] || label="$1"

attempt=1
while true; do
  "$@"
  rc=$?
  [[ $rc -eq 0 ]] && exit 0
  if [[ $attempt -ge $attempts ]]; then
    echo "$(date '+%F %T') retry[$label]: agotados $attempts intentos (rc=$rc)" >&2
    exit $rc
  fi
  delay=$(( base * (2 ** (attempt - 1)) ))
  [[ $delay -gt $maxd ]] && delay=$maxd
  jitter=$(( RANDOM % 1000 ))   # 0..999 ms de jitter para evitar thundering herd
  echo "$(date '+%F %T') retry[$label]: intento $attempt falló (rc=$rc), reintento en ${delay}.${jitter}s" >&2
  sleep "${delay}.${jitter}"
  attempt=$(( attempt + 1 ))
done
