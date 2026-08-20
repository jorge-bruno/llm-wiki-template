#!/usr/bin/env python3
"""Extrae un resumen de las sesiones de Claude Code (JSONL) para la captura diaria del second brain.

Emite JSON estructurado por stdout; la skill `capturar-claude` lo renderiza a raw/claude/YYYY-MM-DD.md.

Uso: python3 extract_claude_sessions.py [dias=auto]
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


# Zona horaria local del vault. Atribuimos cada evento a su fecha *local* (no a la fecha de la
# corrida), lo que evita el sesgo de "lo de anoche cae en el archivo de hoy".
# >>> Ajustá esto a tu zona horaria (ej. ZoneInfo("Europe/Madrid"), ZoneInfo("America/New_York")).
LOCAL_TZ = ZoneInfo("America/Buenos_Aires")


def to_local_date(ts_str: str):
    """Convierte un timestamp ISO (UTC o con offset) a la fecha local. None si no parsea."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ).date()


# Los dirs de ~/.claude/projects codifican el path absoluto del proyecto reemplazando todo lo
# no-alfanumérico por '-'. Derivamos la codificación de TU home para reconocer el proyecto "home".
_HOME = os.path.expanduser("~")
_HOME_ENC = re.sub(r"[^A-Za-z0-9]+", "-", _HOME).strip("-")  # ej. "Users-tu-usuario"

# (Opcional) Nombres de tus repos, para que el proyecto salga con un nombre lindo en vez del path
# codificado. Personalizá esta lista con los tuyos; si la dejás vacía, se usa el fallback de abajo.
KNOWN_REPOS = [
    "data-pipeline",
    "infra-live",
    "analytics-dbt",
]


def get_project_name(proj_dir_name: str) -> str:
    """Convierte el nombre del directorio del proyecto en un nombre legible."""
    norm = proj_dir_name.replace("_", "-").strip("-")
    if norm == _HOME_ENC or norm == f"-{_HOME_ENC}".strip("-"):
        return "home"
    for repo in KNOWN_REPOS:
        if repo in norm:
            return repo
    # Fallback: sacar el prefijo del home y quedarse con el resto.
    clean = norm
    if _HOME_ENC and clean.startswith(_HOME_ENC):
        clean = clean[len(_HOME_ENC):]
    clean = clean.strip("-")
    if not clean:
        return "home"
    return clean.replace("-", "/") if len(clean) < 40 else clean.split("-")[0]


def extract_branch(content_str: str) -> str | None:
    if "Current branch:" in content_str:
        for line in content_str.split("\n"):
            if "Current branch:" in line:
                return line.split("Current branch:")[1].strip()
    return None


def extract_jira_keys(text: str) -> list[str]:
    return list(set(re.findall(r"[A-Z]{2,}-\d+", text)))


def get_text_from_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                texts.append(c.get("text", ""))
        return "\n".join(texts)
    return ""


def is_noise(title: str) -> bool:
    noise_patterns = [
        "<command-name>/model</command-name>",
        "<command-name>/clear</command-name>",
        "<command-name>/login</command-name>",
        "<command-name>/reload-plugins</command-name>",
        "daily-notes",
        "Daily Meeting Notes",
        "<local-command-caveat>",
    ]
    for p in noise_patterns:
        if p in title:
            return True
    if len(title.strip()) < 5:
        return True
    return False


def parse_session(filepath: str) -> dict | None:
    """Devuelve los mensajes de usuario de la sesión con su timestamp crudo, para que
    main() los bucketee por fecha local. Una sesión multi-día aporta a cada fecha que tocó."""
    branch = None
    messages = []  # [{"ts": <iso raw>, "text": <str>}]

    try:
        with open(filepath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                if d.get("type") != "user":
                    continue

                text = get_text_from_content(d.get("message", {}).get("content", ""))
                if not text or text.startswith("<local-command"):
                    continue

                if not branch:
                    b = extract_branch(text)
                    if b:
                        branch = b

                ts = d.get("timestamp")
                if not ts:
                    continue
                # El branch de git (convención <tipo>/PROJ-NNN/<slug>) viene en cada record y es la
                # señal primaria del ticket; los mensajes de usuario suelen ser "dale segui"/"mergeado".
                messages.append({"ts": ts, "text": text[:500], "branch": d.get("gitBranch") or branch})
    except (IOError, OSError):
        return None

    if not messages:
        return None

    return {
        "session_id": os.path.basename(filepath).replace(".jsonl", ""),
        "branch": branch,
        "messages": messages,
    }


def auto_days(today_local, floor=2, ceil=14) -> int:
    """Ventana auto-sanable (watermark): cubre desde la última captura en `raw/claude/` hasta hoy.
    Sin estado extra — los `.md` ya capturados SON la marca de agua: un lunes barre el finde y una
    vuelta de vacaciones barre el gap entero (clamp a `ceil` para no degenerar). Sin capturas → `floor`."""
    raw_dir = _find_raw_claude_dir()
    if not raw_dir:
        return floor
    latest = None
    for name in os.listdir(raw_dir):
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.md$", name)
        if not m:
            continue
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if latest is None or dt > latest:
            latest = dt
    if latest is None:
        return floor
    span = (today_local - latest).days + 1  # inclusivo: latest..hoy
    return max(floor, min(ceil, span))


def _find_raw_claude_dir():
    """`raw/claude/` relativo al cwd (la skill corre desde el root del vault) o al script."""
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(os.getcwd(), "raw", "claude"),
              os.path.join(here, "..", "..", "raw", "claude")):
        if os.path.isdir(c):
            return c
    return None


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "auto"
    today_local = datetime.now(LOCAL_TZ).date()
    # Ventana: "auto" = watermark auto-sanable (desde la última captura hasta hoy); un N explícito
    # fuerza esa cantidad de días-calendario.
    days = auto_days(today_local) if arg == "auto" else max(1, int(arg))
    # Cutoff alineado a medianoche local: cubre `days` días-calendario terminando hoy.
    # (No usamos "ahora - N*24h" porque excluiría sesiones tempranas del día al regenerar.)
    cutoff_date = today_local - timedelta(days=days - 1)
    cutoff_dt = datetime.combine(cutoff_date, datetime.min.time(), tzinfo=LOCAL_TZ)
    base = os.path.expanduser("~/.claude/projects/")

    parsed = []
    for proj_dir in glob.glob(base + "*/"):
        proj_dir_name = os.path.basename(proj_dir.rstrip("/"))
        project = get_project_name(proj_dir_name)
        for jf in glob.glob(proj_dir + "*.jsonl"):
            if "subagents" in jf:
                continue
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(jf), tz=timezone.utc)
                if mtime < cutoff_dt:
                    continue
            except OSError:
                continue
            session = parse_session(jf)
            if session:
                session["project"] = project
                parsed.append(session)

    # Bucketeo por fecha local del evento. Una sesión multi-día aporta una entrada por cada
    # fecha (>= cutoff) en la que tuvo actividad → "dividir por día".
    by_date = {}  # "YYYY-MM-DD" -> [entry]
    for s in parsed:
        # Bucketeo por (fecha local, branch): una sesión que cruza días o temas aporta una entrada
        # por cada combinación. Separa trabajos que si no colapsarían en una sola línea (p.ej. una
        # sesión que abre con un tema y sigue con un refactor de PROJ-215 bajo otro branch).
        groups = {}  # (date, branch) -> [msg]
        for m in s["messages"]:
            d = to_local_date(m["ts"])
            if d is None or d < cutoff_date:
                continue
            br = m.get("branch") or s.get("branch")
            groups.setdefault((d, br), []).append(m)

        for (d, br), msgs in groups.items():
            # Título = primer mensaje no-ruido de ESE día+branch (no el de apertura de la sesión).
            title = None
            for m in msgs:
                line = re.sub(r"<[^>]+>", "", m["text"].split("\n")[0]).strip()
                if line and not is_noise(m["text"]):
                    title = line[:200]
                    break
            if not title:
                continue  # ese bloque solo tuvo ruido (p.ej. /clear) → no aporta entrada

            # Jira key: el branch es la señal primaria (convención <tipo>/PROJ-NNN/<slug>);
            # el texto de los mensajes es complemento.
            jira = list(extract_jira_keys(br)) if br else []
            for m in msgs:
                jira.extend(extract_jira_keys(m["text"]))
            ts_sorted = sorted(m["ts"] for m in msgs)

            by_date.setdefault(d.isoformat(), []).append({
                "project": s["project"],
                "session_id": s["session_id"],
                "branch": br,
                "title": title,
                "jira_keys": sorted(set(jira)),
                "keywords": [m["text"][:80] for m in msgs[:5]],
                "message_count": len(msgs),
                "first_ts": ts_sorted[0],
                "last_ts": ts_sorted[-1],
            })

    for d in by_date:
        by_date[d].sort(key=lambda e: (e["project"], e["first_ts"]))

    out_by_date = {}
    for d in sorted(by_date):
        keys = sorted({k for e in by_date[d] for k in e["jira_keys"]})
        out_by_date[d] = {"jira_keys": keys, "entries": by_date[d]}

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tz": str(LOCAL_TZ),
        "cutoff_date": cutoff_date.isoformat(),
        "days": days,
        "dates": sorted(by_date),
        "by_date": out_by_date,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
