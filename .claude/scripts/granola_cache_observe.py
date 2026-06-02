#!/usr/bin/env python3
"""Observador de eviction del cache de Granola (caracterización, no captura).

Snapshotea la COMPOSICIÓN del cache (`meeting_id` + nº de segmentos + mtime del archivo),
NO el contenido. Appendea una línea compacta a `.claude/logs/granola-cache-observe.log`
(gitignored). Sirve para caracterizar empíricamente cuándo Granola evicta transcripts del
cache rotativo, complementando el análisis estático del bundle.

Uso: python3 granola_cache_observe.py    (un snapshot; correr en loop para serie temporal)
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from granola_extract import load_state, list_available, CACHE_ENC, REPO_ROOT

LOG = os.path.join(REPO_ROOT, ".claude", "logs", "granola-cache-observe.log")


def main() -> int:
    try:
        mtime = time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(CACHE_ENC)))
    except OSError:
        mtime = "??:??:??"
    try:
        meetings = list_available(load_state())
    except Exception as e:  # decrypt/keychain/etc — registrar el fallo, no romper el loop
        line = f"{time.strftime('%F %T')} | ERROR {type(e).__name__}"
        with open(LOG, "a") as f:
            f.write(line + "\n")
        print(line)
        return 1
    parts = " ".join(f"{m['meeting_id'][:8]}:{m['n_segments']}" for m in meetings)
    line = f"{time.strftime('%F %T')} | cache_mtime={mtime} | {len(meetings)} mtgs | {parts}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
