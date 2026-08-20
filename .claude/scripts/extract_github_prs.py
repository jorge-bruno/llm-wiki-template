#!/usr/bin/env python3
"""
extract_github_prs.py — captura PRs de GitHub vía `gh` CLI y emite JSON a stdout.

Uso:
    python extract_github_prs.py [auto|N]

    auto (default): ventana watermark auto-sanable — barre desde la última captura
                    en raw/github/ hasta hoy (clamp 2–14 días).
    N:              cantidad explícita de días a cubrir.

Salida (stdout): JSON estructurado por fecha → repo → lista de PRs.
Logs (stderr):   progreso y errores.

Requiere `gh` autenticado (`gh auth login`) y la lista de repos en
`.claude/config/github-repos.txt` (un OWNER/REPO por línea).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Zona horaria local del vault: cada PR se archiva en la fecha local de su `updatedAt`.
# >>> Ajustá esto a tu zona horaria (ej. ZoneInfo("Europe/Madrid")).
LOCAL_TZ = ZoneInfo("America/Buenos_Aires")

# Jira key regex: 2-6 letras mayúsculas seguidas de guión y dígitos.
# Buscamos en título y headRefName. (Genérico: matchea cualquier prefijo de proyecto.)
_JIRA_RE = re.compile(r"\b([A-Z]{2,6}-\d+)\b")
# Falsos positivos comunes a excluir
_JIRA_EXCLUDE = {"AES-256", "UTF-8", "SHA-256", "SHA-512", "EC-384"}

CONFIG_FILE = Path(__file__).parent.parent / "config" / "github-repos.txt"


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _find_raw_github_dir() -> Path | None:
    here = Path(__file__).resolve().parent
    for candidate in (
        Path(os.getcwd()) / "raw" / "github",
        here.parent.parent / "raw" / "github",
    ):
        if candidate.is_dir():
            return candidate
    return None


def auto_days(today_local, floor: int = 2, ceil: int = 14) -> int:
    """Watermark auto-sanable desde raw/github/ (igual que extract_claude_sessions.py)."""
    raw_dir = _find_raw_github_dir()
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
    span = (today_local - latest).days + 1
    return max(floor, min(ceil, span))


def read_repos() -> list[str]:
    """Lee la lista de repos desde .claude/config/github-repos.txt."""
    if not CONFIG_FILE.exists():
        log(f"ERROR: config no encontrado: {CONFIG_FILE}")
        log("Creá .claude/config/github-repos.txt con un OWNER/REPO por línea.")
        sys.exit(1)
    repos = [
        line.strip()
        for line in CONFIG_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not repos:
        log("ERROR: github-repos.txt está vacío. Agregá repos en formato OWNER/REPO.")
        sys.exit(1)
    return repos


def _resolve_gh() -> str:
    """Ruta absoluta a `gh`. Un scheduler (launchd/cron) corre el pipeline con un PATH mínimo que
    puede no incluir homebrew (`/opt/homebrew/bin`), así que `subprocess.run(["gh", ...])` falla con
    FileNotFoundError en el cron aunque `gh` ande interactivo. Resolvemos la ruta absoluta."""
    found = shutil.which("gh")
    if found:
        return found
    for cand in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh", "/usr/bin/gh"):
        if os.path.exists(cand):
            return cand
    return "gh"  # último recurso: falla con el error habitual, capturado por los callers


GH = _resolve_gh()


def check_gh_auth() -> bool:
    """Verifica que `gh` esté instalado y autenticado."""
    result = subprocess.run(
        [GH, "auth", "status"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log("WARNING: `gh` no está autenticado. Saltando captura de GitHub PRs.")
        return False
    return True


def extract_jira_keys(text: str) -> list[str]:
    """Extrae Jira keys de un texto, filtrando falsos positivos."""
    seen = {}
    for m in _JIRA_RE.finditer(text or ""):
        k = m.group(1)
        if k not in _JIRA_EXCLUDE:
            seen[k] = None  # preserva orden de aparición, deduplica
    return list(seen)


def fetch_prs(repo: str, since_date) -> list[dict] | None:
    """Trae PRs actualizados desde `since_date` (date) vía gh CLI.

    Retorna la lista de PRs parseados o None en caso de error.
    """
    since_str = since_date.strftime("%Y-%m-%d")
    try:
        result = subprocess.run(
            [
                GH, "pr", "list",
                "--repo", repo,
                "--state", "all",
                "--limit", "200",
                "--json",
                "number,title,state,author,createdAt,updatedAt,mergedAt,"
                "url,headRefName,labels,reviewDecision,isDraft",
                "--search", f"updated:>={since_str}",
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
    except FileNotFoundError:
        log("ERROR: `gh` no está instalado en el PATH.")
        return None
    except subprocess.TimeoutExpired:
        log(f"ERROR: timeout al consultar {repo}")
        return None

    if result.returncode != 0:
        log(f"ERROR al consultar {repo}: {result.stderr.strip()}")
        return None

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        log(f"ERROR parseando respuesta de {repo}: {e}")
        return None

    log(f"  {repo}: {len(prs)} PR(s) encontrados")
    return prs


def parse_pr(raw: dict, repo: str) -> dict:
    """Normaliza un PR crudo al formato interno."""
    author = raw.get("author") or {}
    author_login = author.get("login", "") if isinstance(author, dict) else str(author)

    branch = raw.get("headRefName", "")
    title = raw.get("title", "")
    jira_keys = extract_jira_keys(f"{branch} {title}")

    state = raw.get("state", "").lower()  # open / closed / merged
    # gh reporta merged como MERGED en state, o a veces CLOSED con mergedAt
    merged_at = raw.get("mergedAt", "")
    if state == "closed" and merged_at:
        state = "merged"

    labels = [lbl.get("name", "") for lbl in (raw.get("labels") or []) if isinstance(lbl, dict)]

    # updatedAt determina en qué día cae el PR en raw/github/
    updated_at_str = raw.get("updatedAt", "")
    if updated_at_str:
        updated_dt = datetime.fromisoformat(
            updated_at_str.replace("Z", "+00:00")
        ).astimezone(LOCAL_TZ)
    else:
        updated_dt = datetime.now(LOCAL_TZ)

    return {
        "number": raw.get("number"),
        "title": title,
        "state": state,
        "author": author_login,
        "branch": branch,
        "jira_keys": jira_keys,
        "url": raw.get("url", f"https://github.com/{repo}/pull/{raw.get('number')}"),
        "created_at": raw.get("createdAt", ""),
        "updated_at": updated_dt.isoformat(),
        "merged_at": merged_at,
        "is_draft": raw.get("isDraft", False),
        "review_decision": raw.get("reviewDecision", ""),
        "labels": labels,
        "repo": repo,
    }


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "auto"
    today_local = datetime.now(LOCAL_TZ).date()

    days = auto_days(today_local) if arg == "auto" else max(1, int(arg))
    cutoff_date = today_local - timedelta(days=days - 1)

    log(f"extract_github_prs: ventana {days} día(s) desde {cutoff_date}")

    if not check_gh_auth():
        # Salida limpia para que el pipeline no falle
        print(json.dumps({"error": "gh_not_authenticated", "dates": [], "by_date": {}}))
        sys.exit(0)

    repos = read_repos()
    log(f"Repos configurados: {', '.join(repos)}")

    # Estructura de salida: by_date[fecha][repo] = [pr, ...]
    by_date: dict[str, dict[str, list[dict]]] = {}

    for repo in repos:
        log(f"Consultando {repo}...")
        raw_prs = fetch_prs(repo, cutoff_date)
        if raw_prs is None:
            continue  # error ya logueado; seguimos con el siguiente repo

        for raw_pr in raw_prs:
            pr = parse_pr(raw_pr, repo)

            # Bucketear por fecha local de updatedAt
            pr_dt = datetime.fromisoformat(pr["updated_at"])
            date_key = pr_dt.strftime("%Y-%m-%d")

            # Solo incluir si cae dentro de la ventana
            if date_key < str(cutoff_date):
                continue

            by_date.setdefault(date_key, {}).setdefault(repo, []).append(pr)

    dates = sorted(by_date.keys())
    log(f"Fechas con actividad: {dates or '(ninguna)'}")

    output = {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        "tz": str(LOCAL_TZ),
        "cutoff_date": str(cutoff_date),
        "days": days,
        "repos": repos,
        "dates": dates,
        "by_date": by_date,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
