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


STATE_LABELS = {"open": "abierto", "merged": "mergeado", "closed": "cerrado"}

_SENTINEL_RE = re.compile(r"^<!-- pr: (?P<repo>\S+)#(?P<num>\d+) -->$")
_SECTION_RE = re.compile(r"^## (\S+)$")


def _capture_stamp(now: "datetime") -> str:
    """`~HH:Mx ART`: hora exacta, minuto redondeado a la decena (convención de captura del vault)."""
    return f"{now:%H}:{now.minute // 10}x"


def render_pr_bullet(pr: dict) -> str:
    """Sentinel `<!-- pr: owner/repo#N -->` + bullet, exactamente como lo renderiza capturar-github."""
    state_word = "draft" if pr.get("is_draft") else STATE_LABELS.get(pr["state"], pr["state"])
    state = f"**{state_word}**"
    review = pr.get("review_decision") or ""
    if review == "APPROVED":
        state += " ✓ aprobado"
    elif review == "CHANGES_REQUESTED":
        state += " ⚑ cambios solicitados"
    # Algunos PRs (release-please, bots) traen el título de GitHub ya terminado en "(PROJ-NNN)":
    # lo sacamos de ahí para no duplicarlo con el paréntesis de jira_keys que agregamos nosotros.
    title = re.sub(r"\s*\([A-Z]{2,6}-\d+(?:,\s*[A-Z]{2,6}-\d+)*\)\s*$", "", pr["title"])
    jira = f" ({', '.join(pr['jira_keys'])})" if pr.get("jira_keys") else ""
    sentinel = f"<!-- pr: {pr['repo']}#{pr['number']} -->"
    bullet = (
        f"- **PR #{pr['number']}** · `{pr['branch']}` · {state} · @{pr['author']} — "
        f"{title}{jira} *(fuente: [#{pr['number']}]({pr['url']}))*"
    )
    return f"{sentinel}\n{bullet}"


def render_header(today_local, days: int, repos: list[str]) -> list[str]:
    now = datetime.now(AR_TZ)
    repo_names = ", ".join(r.split("/", 1)[1] if "/" in r else r for r in repos)
    return [
        f"> **Fuente**: GitHub PRs (`gh`) · **Capturado**: {today_local.isoformat()} "
        f"(~{_capture_stamp(now)} ART) · repos: {repo_names} · ventana: {days} día(s)",
        "",
    ]


def _render_sections(section_order: list[str], sections: dict[str, dict[int, str]]) -> list[str]:
    lines: list[str] = []
    for repo in section_order:
        blocks = sections.get(repo) or {}
        if not blocks:
            continue
        lines.append(f"## {repo}")
        lines.append("")
        for num in sorted(blocks, reverse=True):
            lines.append(blocks[num])
        lines.append("")
    return lines


def render_date_file(date_str: str, by_repo: dict[str, list[dict]], today_local, days: int,
                      repos: list[str]) -> str:
    """Render completo (archivo de hoy, o archivo previo que todavía no existía)."""
    sections = {repo: {pr["number"]: render_pr_bullet(pr) for pr in prs} for repo, prs in by_repo.items()}
    # Orden de secciones: el de `repos` (config), restringido a los que tuvieron actividad ese día.
    order = [r for r in repos if r in sections] + [r for r in sections if r not in repos]
    lines = render_header(today_local, days, repos)
    lines.append(f"# GitHub PRs — {date_str}")
    lines.append("")
    lines.extend(_render_sections(order, sections))
    return "\n".join(lines).rstrip() + "\n"


def parse_existing_prs(text: str) -> tuple[dict[str, dict[int, str]], list[str]]:
    """Parsea un `raw/github/<fecha>.md` existente en {repo: {numero: bloque}} + orden de secciones."""
    lines = text.split("\n")
    sections: dict[str, dict[int, str]] = {}
    order: list[str] = []
    current_repo = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _SECTION_RE.match(line)
        if m:
            current_repo = m.group(1)
            if current_repo not in sections:
                sections[current_repo] = {}
                order.append(current_repo)
            i += 1
            continue
        sm = _SENTINEL_RE.match(line)
        if sm and current_repo is not None:
            num = int(sm.group("num"))
            block = line
            if i + 1 < len(lines):
                block += "\n" + lines[i + 1]
                i += 2
            else:
                i += 1
            sections[current_repo][num] = block
            continue
        i += 1
    return sections, order


def merge_date_file(date_str: str, by_repo: dict[str, list[dict]], existing_text: str, today_local,
                     days: int, repos: list[str]) -> str:
    """Mergea el bucket fresco sobre un archivo de un día previo ya existente: upsert por sentinel,
    preserva todo lo que no está en el bucket fresco (PRs migrados de bucket en corridas previas)."""
    sections, order = parse_existing_prs(existing_text)
    for repo, prs in by_repo.items():
        if repo not in sections:
            sections[repo] = {}
            order.append(repo)
        for pr in prs:
            sections[repo][pr["number"]] = render_pr_bullet(pr)
    lines = render_header(today_local, days, repos)
    lines.append(f"# GitHub PRs — {date_str}")
    lines.append("")
    lines.extend(_render_sections(order, sections))
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(output: dict, out_dir: Path, today_local) -> list[str]:
    repos = output["repos"]
    days = output["days"]
    written: list[str] = []
    for date_str in output["dates"]:
        by_repo = output["by_date"].get(date_str, {})
        path = out_dir / f"{date_str}.md"
        if date_str == today_local.isoformat() or not path.exists():
            content = render_date_file(date_str, by_repo, today_local, days, repos)
        else:
            content = merge_date_file(date_str, by_repo, path.read_text(), today_local, days, repos)
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        written.append(str(path))
    return written


def main() -> None:
    argv = sys.argv[1:]
    markdown_mode = "--markdown" in argv
    if markdown_mode:
        argv.remove("--markdown")
    out_dir_arg = None
    if "--out-dir" in argv:
        idx = argv.index("--out-dir")
        out_dir_arg = argv[idx + 1]
        del argv[idx:idx + 2]
    arg = argv[0] if argv else "auto"
    today_local = datetime.now(LOCAL_TZ).date()

    days = auto_days(today_local) if arg == "auto" else max(1, int(arg))
    cutoff_date = today_local - timedelta(days=days - 1)

    log(f"extract_github_prs: ventana {days} día(s) desde {cutoff_date}")

    if not check_gh_auth():
        # Salida limpia para que el pipeline no falle
        if markdown_mode:
            print(json.dumps({"error": "gh_not_authenticated", "markdown": True, "written": []}))
        else:
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

    if markdown_mode:
        out_dir = Path(out_dir_arg) if out_dir_arg else (_find_raw_github_dir() or Path("raw/github"))
        written = write_markdown(output, out_dir, today_local)
        for w in written:
            log(f"escrito: {w}")
        print(json.dumps({"markdown": True, "written": written, "dates": dates}, ensure_ascii=False))
        return

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
