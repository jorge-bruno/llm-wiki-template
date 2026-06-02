#!/usr/bin/env python3
"""Extrae un resumen de las sesiones de Claude Code (JSONL) para la captura diaria del second brain.

Emite JSON estructurado por stdout; la skill `capturar-claude` lo renderiza a raw/claude/YYYY-MM-DD.md.

Uso: python3 extract_claude_sessions.py [dias=1]
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone


# Zona horaria local para atribuir cada evento a su fecha *local* (no a la fecha de la corrida;
# evita el sesgo de "lo de anoche cae en el archivo de hoy"). Ajustá el offset a tu zona.
# (UTC-3 = Buenos Aires, sin DST. Para otra zona, cambiá hours.)
LOCAL_TZ = timezone(timedelta(hours=-3))


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


# Claude Code codifica el path absoluto del proyecto en el nombre del dir de ~/.claude/projects,
# reemplazando todo carácter no-alfanumérico por '-'. Derivamos el prefijo del home dinámicamente
# para mapear el path a un nombre legible (en vez de hardcodear un usuario concreto).
HOME_DIR_PREFIX = re.sub(r"[^a-zA-Z0-9]", "-", os.path.expanduser("~"))

# OPCIONAL: agregá acá los nombres de tus repos para que aparezcan con nombre prolijo en la captura.
# Si lo dejás vacío, el fallback deriva un nombre razonable del path igual. Ej:
#   KNOWN_REPOS = ["mi-repo-infra", "mi-repo-dbt", "llm-wiki"]
KNOWN_REPOS: list[str] = []


def get_project_name(proj_dir_name: str) -> str:
    """Convierte el nombre del directorio del proyecto en un nombre legible."""
    if proj_dir_name in (HOME_DIR_PREFIX, HOME_DIR_PREFIX + "-"):
        return "home"
    norm = proj_dir_name.replace("_", "-")
    for repo in KNOWN_REPOS:
        if repo in norm:
            return repo
    # Fallback: sacar el prefijo del home y quedarse con el resto.
    clean = proj_dir_name
    if clean.startswith(HOME_DIR_PREFIX + "-"):
        clean = clean[len(HOME_DIR_PREFIX) + 1:]
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
                messages.append({"ts": ts, "text": text[:500]})
    except (IOError, OSError):
        return None

    if not messages:
        return None

    return {
        "session_id": os.path.basename(filepath).replace(".jsonl", ""),
        "branch": branch,
        "messages": messages,
    }


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    today_local = datetime.now(LOCAL_TZ).date()
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
        msgs_by_date = {}
        for m in s["messages"]:
            d = to_local_date(m["ts"])
            if d is None or d < cutoff_date:
                continue
            msgs_by_date.setdefault(d, []).append(m)

        for d, msgs in msgs_by_date.items():
            # Título = primer mensaje no-ruido de ESE día (no el de apertura de la sesión).
            title = None
            for m in msgs:
                line = re.sub(r"<[^>]+>", "", m["text"].split("\n")[0]).strip()
                if line and not is_noise(m["text"]):
                    title = line[:200]
                    break
            if not title:
                continue  # ese día solo tuvo ruido (p.ej. /clear) → no aporta entrada

            jira = list(extract_jira_keys(s["branch"])) if s.get("branch") else []
            for m in msgs:
                jira.extend(extract_jira_keys(m["text"]))
            ts_sorted = sorted(m["ts"] for m in msgs)

            by_date.setdefault(d.isoformat(), []).append({
                "project": s["project"],
                "session_id": s["session_id"],
                "branch": s.get("branch"),
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
        "tz": "local (UTC-3 por defecto; configurable en LOCAL_TZ)",
        "cutoff_date": cutoff_date.isoformat(),
        "days": days,
        "dates": sorted(by_date),
        "by_date": out_by_date,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
