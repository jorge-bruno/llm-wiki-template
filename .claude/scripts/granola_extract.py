#!/usr/bin/env python3
"""Extrae transcripts verbatim de Granola desde el cache local cifrado.

Granola guarda el transcript completo de cada meeting reciente en
`~/Library/Application Support/Granola/cache-v6.json.enc`, cifrado con AES-256-GCM.
La llave (DEK de 32B) está en `storage.dek`, envuelta por Electron safeStorage con
una llave del Keychain de macOS (item "Granola Safe Storage"). El MCP remoto gatea
el transcript por tier pago; este script lo recupera localmente, sin el MCP.

El cache es un working-set ROTATIVO (solo retiene meetings recientes), por eso este
script está pensado para correr seguido (watcher en cada escritura del cache) y es
idempotente: deduplica por `meeting_id` contra los .md ya escritos en raw/granola/.

Modos:
  granola_extract.py                  captura todos los meetings nuevos del cache
  granola_extract.py --list           imprime (JSON) los meetings disponibles en el cache
  granola_extract.py <meeting_id>     (re)captura un meeting puntual, sobrescribiendo

La contraseña/llave NUNCA se imprime. Salida JSON a stdout; logs a stderr.

Requiere `cryptography` (usar el venv en .claude/scripts/granola-venv/).
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

GRANOLA_DIR = os.path.expanduser("~/Library/Application Support/Granola")
CACHE_ENC = os.path.join(GRANOLA_DIR, "cache-v6.json.enc")
DEK_FILE = os.path.join(GRANOLA_DIR, "storage.dek")
KEYCHAIN_SERVICE = "Granola Safe Storage"

# Buenos Aires es UTC-3 todo el año (sin DST desde 2009).
ART = timezone(timedelta(hours=-3))

# repo root = .../<vault>/.claude/scripts/granola_extract.py  ->  subir 3 niveles
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(REPO_ROOT, "raw", "granola")


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# --------------------------------------------------------------------------- #
# Descifrado
# --------------------------------------------------------------------------- #
def get_dek() -> bytes:
    """Recupera la DEK de 32 bytes. Lanza RuntimeError con mensaje claro si falla."""
    try:
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as e:
        raise RuntimeError(
            "Falta el paquete 'cryptography'. Corré el script con el venv: "
            ".claude/scripts/granola-venv/bin/python .claude/scripts/granola_extract.py"
        ) from e

    try:
        pw = subprocess.check_output(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"No se pudo leer el Keychain (item '{KEYCHAIN_SERVICE}'). "
            "Verificá que Granola esté instalado y que se haya dado 'Always Allow' "
            "al acceso del binario `security`."
        ) from e
    if not pw:
        raise RuntimeError(f"El item '{KEYCHAIN_SERVICE}' del Keychain vino vacío.")

    # Chromium safeStorage (macOS): PBKDF2-HMAC-SHA1, salt fijo, AES-128-CBC, IV=16 espacios
    key = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1003).derive(pw)
    blob = open(DEK_FILE, "rb").read()
    if blob[:3] != b"v10":
        raise RuntimeError(f"storage.dek no tiene el prefijo safeStorage 'v10' (got {blob[:3]!r}).")
    dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    pt = dec.update(blob[3:]) + dec.finalize()
    pad = pt[-1]
    if 1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad:
        pt = pt[:-pad]
    dek = base64.b64decode(pt.decode())
    if len(dek) != 32:
        raise RuntimeError(f"DEK con longitud inesperada ({len(dek)}B, se esperaban 32).")
    return dek


def load_state() -> dict:
    """Descifra el cache y devuelve cache.state."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    dek = get_dek()
    data = open(CACHE_ENC, "rb").read()
    # AES-256-GCM: nonce 12B (prefijo) + ciphertext + tag 16B (sufijo)
    plain = AESGCM(dek).decrypt(data[:12], data[12:], None)
    return json.loads(plain)["cache"]["state"]


# --------------------------------------------------------------------------- #
# Modelo de meetings
# --------------------------------------------------------------------------- #
def meeting_index(state: dict) -> dict:
    """meeting_id -> metadata {title, created_at, attendees} desde recentMeetings."""
    idx = {}
    rm = (state.get("multiChatState") or {}).get("chatContext") or {}
    for m in rm.get("recentMeetings") or []:
        if m.get("id"):
            idx[m["id"]] = m
    return idx


def list_available(state: dict) -> list[dict]:
    """Meetings con transcript cacheado, con su metadata si está disponible."""
    transcripts = state.get("transcripts") or {}
    idx = meeting_index(state)
    out = []
    for mid, segs in transcripts.items():
        meta = idx.get(mid, {})
        out.append({
            "meeting_id": mid,
            "title": meta.get("title") or "(sin título)",
            "created_at": meta.get("created_at"),
            "attendees": [a.get("name") or a.get("email") for a in (meta.get("attendees") or [])],
            "n_segments": len(segs) if isinstance(segs, list) else 0,
        })
    return out


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def _slug(title: str) -> str:
    s = (title or "").lower()
    s = s.replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "meeting"


def _to_art(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ART)
    except ValueError:
        return None


def _source_label(source: str, detected: str | None) -> str:
    if detected:
        return detected
    return {"microphone": "Mic", "system": "Sistema"}.get(source, source or "?")


def render_transcript(segments: list[dict]) -> str:
    """Renderiza los segmentos verbatim, agrupando turnos consecutivos del mismo hablante."""
    lines: list[str] = []
    cur_label: str | None = None
    cur_ts: datetime | None = None
    cur_text: list[str] = []

    def flush():
        if cur_text:
            hhmmss = cur_ts.strftime("%H:%M:%S") if cur_ts else "--:--:--"
            body = " ".join(t.strip() for t in cur_text if t.strip())
            lines.append(f"**[{hhmmss}] {cur_label}**")
            lines.append(body)
            lines.append("")

    for s in segments:
        label = _source_label(s.get("source"), s.get("detected_speaker_name"))
        if label != cur_label:
            flush()
            cur_label = label
            cur_ts = _to_art(s.get("start_timestamp"))
            cur_text = []
        cur_text.append(s.get("text") or "")
    flush()
    return "\n".join(lines).strip()


def build_markdown(meeting: dict, segments: list[dict]) -> tuple[str, str]:
    """Devuelve (filepath, contenido) para un meeting."""
    raw_title = meeting.get("title")
    title = raw_title or "(sin título)"
    created = _to_art(meeting.get("created_at"))
    first_seg = _to_art(segments[0].get("start_timestamp")) if segments else None
    last_seg = _to_art(segments[-1].get("end_timestamp")) if segments else None
    day = (created or first_seg or datetime.now(ART)).strftime("%Y-%m-%d")
    # Sin título, el slug incluye el meeting_id: evita que dos meetings sin título el mismo
    # día colisionen en el mismo archivo (find_existing dedupea por id, no por nombre).
    slug = _slug(raw_title) if raw_title else f"sin-titulo-{meeting['meeting_id'][:8]}"
    fname = f"{day}-{slug}.md"
    fpath = os.path.join(RAW_DIR, fname)

    attendees = [a.get("name") or a.get("email") for a in (meeting.get("attendees") or [])]
    att_yaml = ", ".join(a for a in attendees if a)

    span = ""
    if first_seg and last_seg:
        span = f"{first_seg.strftime('%H:%M')}–{last_seg.strftime('%H:%M')} (UTC-3)"

    header = [
        "---",
        f"meeting_id: {meeting['meeting_id']}",
        f"fecha: {day}",
        "fuente: granola",
        f"attendees: [{att_yaml}]",
        f"segments: {len(segments)}",
        "origen: cache-local",
        "---",
        "",
        f"# {title} — {day}",
        "",
        f"**Attendees**: {att_yaml or '(no informados)'}",
        "",
        "> [!note] Transcript verbatim recuperado del cache local de Granola "
        "(`cache-v6.json.enc`), no del MCP.",
        f"> {len(segments)} segmentos"
        + (f" · {span}" if span else "")
        + " · fuentes: **Mic** (micrófono local) / **Sistema** (audio remoto). "
        "Granola free no diariza, así que las etiquetas son la fuente de audio, no el hablante.",
        "",
        "## Transcript",
        "",
        "",
    ]
    return fpath, "\n".join(header) + render_transcript(segments) + "\n"


# --------------------------------------------------------------------------- #
# Dedupe / escritura
# --------------------------------------------------------------------------- #
def find_existing(meeting_id: str) -> str | None:
    """Devuelve el path del .md que ya tiene este meeting_id, o None."""
    if not os.path.isdir(RAW_DIR):
        return None
    needle = f"meeting_id: {meeting_id}"
    for name in os.listdir(RAW_DIR):
        if not name.endswith(".md"):
            continue
        p = os.path.join(RAW_DIR, name)
        try:
            with open(p, encoding="utf-8") as f:
                head = f.read(512)
        except OSError:
            continue
        if needle in head:
            return p
    return None


def _saved_segments(path: str) -> int | None:
    """Cuántos segmentos tiene un .md ya capturado: `segments:` del frontmatter
    (formato nuevo) o el callout `> N segmentos` (capturas viejas). None si no se puede leer."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(2048)
    except OSError:
        return None
    m = re.search(r"^segments:\s*(\d+)", head, re.MULTILINE) or re.search(r"(\d+)\s+segmentos", head)
    return int(m.group(1)) if m else None


def capture(meeting: dict, segments: list[dict], overwrite: bool) -> dict:
    existing = find_existing(meeting["meeting_id"])
    if existing and not overwrite:
        # Idempotente, pero NO congela: si el cache tiene más segmentos que lo guardado
        # (meeting en curso/creciendo), re-capturar. Solo skipear si ya está completo.
        saved = _saved_segments(existing)
        if saved is None or saved >= len(segments):
            return {"meeting_id": meeting["meeting_id"], "status": "skipped",
                    "archivo": os.path.relpath(existing, REPO_ROOT)}
    fpath, content = build_markdown(meeting, segments)
    target = existing or fpath  # si ya existía con otro nombre, sobreescribir ese
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return {
        "meeting_id": meeting["meeting_id"],
        "status": ("overwritten" if overwrite else "updated") if existing else "captured",
        "archivo": os.path.relpath(target, REPO_ROOT),
        "titulo": meeting.get("title"),
        "n_segments": len(segments),
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    arg = argv[1] if len(argv) > 1 else None
    try:
        state = load_state()
    except RuntimeError as e:
        log(f"ERROR: {e}")
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1

    transcripts = state.get("transcripts") or {}
    idx = meeting_index(state)

    if arg == "--list":
        print(json.dumps(list_available(state), ensure_ascii=False, indent=2))
        return 0

    results = []
    if arg:  # meeting_id puntual -> overwrite
        segs = transcripts.get(arg)
        if not segs:
            msg = f"El meeting {arg} no está en el cache (¿evictado? el cache solo retiene recientes)."
            log(f"ERROR: {msg}")
            print(json.dumps({"error": msg}, ensure_ascii=False))
            return 1
        meeting = idx.get(arg, {"meeting_id": arg, "title": None, "created_at": None, "attendees": []})
        meeting["meeting_id"] = arg
        results.append(capture(meeting, segs, overwrite=True))
    else:  # todos los nuevos
        if not transcripts:
            log("No hay transcripts en el cache (Granola no abierto o sin meetings recientes).")
        for mid, segs in transcripts.items():
            meeting = idx.get(mid, {"meeting_id": mid, "title": None, "created_at": None, "attendees": []})
            meeting["meeting_id"] = mid
            results.append(capture(meeting, segs, overwrite=False))

    for r in results:
        log(f"  [{r['status']}] {r.get('archivo')} ({r.get('n_segments','?')} seg)")
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
