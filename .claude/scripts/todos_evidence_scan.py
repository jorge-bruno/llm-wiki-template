#!/usr/bin/env python3
"""
todos_evidence_scan.py — evidencia determinística de cierre/dedupe para la skill `todos`.

Reemplaza la lectura de bitácoras COMPLETAS en cada corrida de /todos (grooming de cierre y
dedupe de candidatos) por un scan determinista que solo emite las LÍNEAS candidatas a evidencia
de entrega. El LLM sigue siendo quien juzga si una línea realmente cierra el TODO — este script
solo reduce qué hay que leer.

Solo LEE bitacora/*.md y todos/*.md. Nunca los modifica ni borra.

Modos:
  groom   — para cada TODO abierto (estado in {pendiente, en-progreso}), escanea las bitácoras
            desde `created` hasta hoy (tope 14 días) buscando evidencia de cierre.
            Uso: python3 todos_evidence_scan.py groom [--max-days 14]

  dedupe  — para una lista de acciones candidatas (una por línea, opcionalmente
            "<titulo>\t<proyecto>"), escanea las últimas N bitácoras (default 3) buscando si el
            candidato ya aparece como entregado.
            Uso: python3 todos_evidence_scan.py dedupe [--last 3] < candidatos.txt
            o:   python3 todos_evidence_scan.py dedupe --candidatos "titulo1" "titulo2\tPROJ-170"

Salida: JSON a stdout. Por cada TODO/candidato: {archivo|candidato, proyecto, matches:
[{bitacora, linea_nro, texto_linea, razon}]}. Solo las líneas que matchean, nunca el archivo
entero.

Sin dependencias nuevas (stdlib). Determinista.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

VAULT = Path(__file__).resolve().parent.parent.parent
TODOS_DIR = VAULT / "todos"
BITACORA_DIR = VAULT / "bitacora"

OPEN_STATES = {"pendiente", "en-progreso"}

# Verbos de cierre — lista conservadora (ver todos/SKILL.md, pasos 2 y 4a). Ampliable, pero se
# prefiere subcobertura (falsos negativos, el LLM no ve la línea) sobre sobrecobertura (falsos
# positivos de cierre).
CLOSURE_VERBS = [
    "mergeado", "mergeó", "mergeada", "se mergeó", "quedó mergeado", "merged",
    "completó", "completado", "se completó",
    "finalizó", "finalizado", "se finalizó",
    "cerró", "cerrado", "se cerró",
    "implementó y verificó",
    "resuelto", "resolvió", "se resolvió",
    "aplicado", "aplicó", "se aplicó",
    "deployado", "deployó", "desplegado", "se deployó",
    "entregado", "entregó",
    "se subió el pr", "subió el pr", "abrió el pr",
    "terminó", "terminado", "terminada", "se terminó",
    "quedó listo", "quedó lista",
    "done",
]

# Stopwords español + algunas de inglés que aparecen en títulos técnicos del vault. Se filtran al
# tokenizar el título de la acción para quedarnos con sustantivos/siglas distintivos.
STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "en", "para", "con", "un", "una", "unos", "unas",
    "y", "a", "al", "que", "por", "se", "su", "sus", "lo", "le", "les", "es", "ya", "no", "si",
    "sin", "sobre", "entre", "hacia", "desde", "hasta", "como", "más", "mas", "pero", "o", "u",
    "the", "and", "for", "with", "from", "into", "onto", "this", "that", "vía", "via",
}


def parse_frontmatter(text: str) -> Optional[tuple]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return None
    return m.group(1), m.group(2)


def fm_val(fm: str, key: str) -> str:
    # [ \t]* (no \n) tras los ":" — si el valor está vacío, \s* se comería el salto de línea
    # y capturaría la línea siguiente del frontmatter (bug real, corregido).
    r = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", fm, re.MULTILINE)
    return r.group(1).strip() if r else ""


def parse_date(s: str) -> Optional[date]:
    s = s.strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def load_todo(path: Path) -> Optional[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    parsed = parse_frontmatter(text)
    if parsed is None:
        return None
    fm, body = parsed
    estado = fm_val(fm, "estado")
    title_m = re.search(r"^# (.+)$", body, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else path.stem.replace("-", " ")
    return {
        "path": path,
        "slug": path.stem,
        "estado": estado,
        "proyecto": fm_val(fm, "proyecto"),
        "created": parse_date(fm_val(fm, "created")),
        "title": title,
        # Un TODO groomeado varias veces acumula secciones "## Sync Jira"/"## Grooming" que
        # mencionan OTRAS keys Jira a propósito para decir que NO aplican ("ninguno toca PROJ-521").
        # Si escaneáramos el body completo por regex, esas keys ajenas contaminarían el matching.
        # Cortamos en el primer "## " (inicio de la primera sección appendeada) para quedarnos
        # solo con la descripción original del TODO.
        "body": body.split("\n## ", 1)[0],
    }


def jira_keys(proyecto: str, body: str) -> list:
    keys = []
    if re.match(r"^[A-Z]{2,10}-\d+$", proyecto):
        keys.append(proyecto)
    for m in re.finditer(r"\b([A-Z]{2,10}-\d+)\b", body):
        if m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def distinctive_tokens(title: str, max_tokens: int = 4) -> list:
    """3-4 sustantivos/siglas más distintivos del título, para el fallback de matching sin Jira key.

    Convención del vault: el título de un TODO empieza con el verbo ("acción, verbo primero" —
    ver todos/SKILL.md paso 3). Ese primer verbo nunca es distintivo (es genérico: revisar,
    implementar, migrar...) y en español, al ir en mayúscula solo por estar al inicio de oración,
    puede colar como falso "sustantivo capitalizado". Se descarta siempre. Entre el resto, se
    prioriza: siglas (todo mayúsculas, cortas) > sustantivos propios (capitalizados) > el resto
    por longitud.
    """
    words = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ0-9_]+", title)
    if words:
        words = words[1:]  # descartar el verbo inicial
    seen = set()
    candidates = []
    for w in words:
        lw = w.lower()
        if len(w) < 3 or lw in STOPWORDS or lw in seen:
            continue
        seen.add(lw)
        candidates.append(w)

    def rank(w: str) -> int:
        if w.isupper() and len(w) <= 8:
            return 0  # sigla: PROJ, API, IAM, KMS...
        if w[0].isupper():
            return 1  # sustantivo propio capitalizado
        return 2

    candidates.sort(key=lambda w: (rank(w), -len(w)))
    return candidates[:max_tokens]


def line_has_closure_verb(line_lower: str) -> bool:
    return any(v in line_lower for v in CLOSURE_VERBS)


def match_line(line: str, keys: list, tokens: list) -> Optional[str]:
    """Devuelve la razón del match ('key:PROJ-170' o 'tokens:IAM,KMS,...') o None."""
    lower = line.lower()
    if not line_has_closure_verb(lower):
        return None
    for k in keys:
        if k in line:
            return f"key:{k}"
    if tokens:
        needed = min(3, len(tokens))
        hits = [t for t in tokens if t.lower() in lower]
        if len(hits) >= needed:
            return f"tokens:{','.join(hits)}"
    return None


def scan_bitacoras(bitacora_paths: list, keys: list, tokens: list) -> list:
    matches = []
    for bpath in bitacora_paths:
        try:
            lines = bpath.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            reason = match_line(line, keys, tokens)
            if reason:
                matches.append({
                    "bitacora": f"bitacora/{bpath.name}",
                    "linea_nro": i,
                    "texto_linea": line.strip(),
                    "razon": reason,
                })
    return matches


def bitacoras_in_range(start: date, end: date) -> list:
    out = []
    for p in sorted(BITACORA_DIR.glob("*.md")):
        d = parse_date(p.stem)
        if d is None:
            continue
        if start <= d <= end:
            out.append(p)
    return out


def last_n_bitacoras(n: int) -> list:
    return sorted(BITACORA_DIR.glob("*.md"))[-n:]


def cmd_groom(max_days: int) -> dict:
    today = date.today()
    results = []
    for path in sorted(TODOS_DIR.glob("*.md")):
        todo = load_todo(path)
        if todo is None or todo["estado"] not in OPEN_STATES:
            continue
        created = todo["created"]
        floor = today - timedelta(days=max_days - 1)  # tope de max_days días, hoy incluido
        start = max(created, floor) if created else floor
        bpaths = bitacoras_in_range(start, today)
        keys = jira_keys(todo["proyecto"], todo["body"])
        tokens = distinctive_tokens(todo["title"])
        matches = scan_bitacoras(bpaths, keys, tokens)
        results.append({
            "archivo_todo": f"todos/{todo['slug']}.md",
            "proyecto": todo["proyecto"] or None,
            "created": created.isoformat() if created else None,
            "ventana": {
                "desde": start.isoformat(),
                "hasta": today.isoformat(),
                "bitacoras_escaneadas": len(bpaths),
            },
            "keys_buscadas": keys,
            "tokens_buscados": tokens,
            "matches": matches,
        })
    return {"modo": "groom", "total_todos_abiertos": len(results), "resultados": results}


def parse_candidate_line(line: str) -> Optional[tuple]:
    line = line.rstrip("\n")
    if not line.strip():
        return None
    parts = line.split("\t")
    title = parts[0].strip()
    proyecto = parts[1].strip() if len(parts) > 1 else ""
    return title, proyecto


def cmd_dedupe(last: int, candidatos: list) -> dict:
    bpaths = last_n_bitacoras(last)
    results = []
    for title, proyecto in candidatos:
        keys = jira_keys(proyecto, title)
        tokens = distinctive_tokens(title)
        matches = scan_bitacoras(bpaths, keys, tokens)
        results.append({
            "candidato": title,
            "proyecto": proyecto or None,
            "keys_buscadas": keys,
            "tokens_buscados": tokens,
            "matches": matches,
        })
    return {
        "modo": "dedupe",
        "bitacoras_escaneadas": [f"bitacora/{p.name}" for p in bpaths],
        "resultados": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="modo", required=True)

    p_groom = sub.add_parser("groom", help="grooming de cierre de TODOs abiertos")
    p_groom.add_argument("--max-days", type=int, default=14, help="tope de días hacia atrás (default 14)")

    p_dedupe = sub.add_parser("dedupe", help="dedupe de candidatos nuevos contra bitácoras recientes")
    p_dedupe.add_argument("--last", type=int, default=3, help="cuántas bitácoras recientes escanear (default 3)")
    p_dedupe.add_argument("--candidatos", nargs="*", default=None,
                           help="candidatos como args ('titulo' o 'titulo\\tPROJ-NNN'); si se omite, lee stdin")

    args = ap.parse_args()

    if args.modo == "groom":
        out = cmd_groom(args.max_days)
    else:
        if args.candidatos:
            raw_lines = args.candidatos
        else:
            raw_lines = sys.stdin.read().splitlines()
        candidatos = [c for c in (parse_candidate_line(l) for l in raw_lines) if c is not None]
        out = cmd_dedupe(args.last, candidatos)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
