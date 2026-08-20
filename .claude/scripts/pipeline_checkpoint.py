#!/usr/bin/env python3
"""
pipeline_checkpoint.py — checkpoint por-tier de los pipelines del vault (refresh / pipeline-diario).

Permite que una corrida headless retome desde el último tier completado en vez de reiniciar:
cada tier se marca al terminar; si una sesión `claude -p` muere a mitad y se la reinvoca dentro
de la ventana de resume (TTL), `start` devuelve qué tiers saltear.

Cada pipeline tiene su propio archivo de checkpoint (`.claude/logs/.pipeline-checkpoint.<pipeline>.json`,
gitignored, efímero por corrida) — así una corrida de `refresh` y una de `pipeline-diario` que se
solapan en el tiempo (ej. el cron horario vs. el cron matutino) no se pisan el progreso entre sí.

Verbos:
    start <pipeline> [--ttl SEGUNDOS]
        Asegura un checkpoint para <pipeline>. Si el checkpoint previo de ESE pipeline no está
        terminado y es fresco (dentro del TTL) → RESUME (conserva el progreso). Si está terminado
        o es viejo → arranca uno nuevo.
        Imprime JSON: {pipeline, run_id, resumed, skip:[tiers ya hechos], pending:[tiers a correr]}

    mark <pipeline> <tier> <status> [detalle...]
        status ∈ done | regenerated | skipped | deferred | failed. Registra ts + detalle del tier.
        `deferred` = la fuente está sana pero esta sesión no pudo usarla (su MCP no quedó enumerado, o
        el proxy se cayó): NO cuenta como resuelto → se reintenta al resumir. Distinto de `skipped`,
        que es un descarte legítimo (falta auth, `gh` ausente) y no se reintenta.

    done <pipeline>
        Marca la corrida como terminada (la próxima `start` arranca limpia).

    reopen <pipeline>
        Si hay tiers `deferred`, reabre la corrida para reintentarlos en una sesión nueva: pone
        `finished=false`, refresca la ventana de resume y resetea a `pending` el primer tier diferido y
        todos los posteriores del orden canónico (los downstream tienen que rehacerse para incorporar
        lo que se recapture). Imprime JSON y sale 0 si reabrió, 1 si no había nada diferido — así el
        wrapper de launchd decide con el exit code si relanza la sesión.

    summary <pipeline> [--format md|json]
        Imprime el resumen por-tier (regenerado vs. salteado). md por default.

    show <pipeline>
        Vuelca el JSON crudo del checkpoint.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

# Zona horaria local del vault. >>> Ajustá a la tuya (ej. ZoneInfo("Europe/Madrid")).
LOCAL_TZ = ZoneInfo("America/Buenos_Aires")
ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = ROOT / ".claude" / "logs"
DEFAULT_TTL = 1800  # 30 min: una reinvocación tras crash resume; una corrida horaria normal arranca limpia.

# Orden canónico de tiers por pipeline. La bitácora puede correrse 2 veces (ayer+hoy / re-pass tras Tier2);
# se trata como un único tier "bitacora".
PIPELINES = {
    "refresh": ["granola", "claude", "slack", "github", "bitacora", "todos", "compactar", "backup"],
    "pipeline-diario": ["claude", "bitacora", "granola", "slack", "github", "calendar", "todos", "compactar", "backup"],
}

# Estados que cuentan como "ya resuelto" → se saltean al resumir. `failed` y `deferred` se reintentan.
RESOLVED = {"done", "regenerated", "skipped"}
EMOJI = {"done": "✅", "regenerated": "🔁", "skipped": "⏭️", "deferred": "🕓", "failed": "❌", "pending": "⏳"}


def _now_iso() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def _checkpoint_path(pipeline: str) -> Path:
    return LOGS_DIR / f".pipeline-checkpoint.{pipeline}.json"


def _load(pipeline: str) -> Optional[dict]:
    path = _checkpoint_path(pipeline)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _save(pipeline: str, data: dict) -> None:
    path = _checkpoint_path(pipeline)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _new_checkpoint(pipeline: str, tiers: list[str]) -> dict:
    return {
        "pipeline": pipeline,
        "run_id": datetime.now(LOCAL_TZ).strftime("%Y%m%dT%H%M%S"),
        "started": _now_iso(),
        "started_epoch": time.time(),
        "finished": False,
        "tiers": {t: {"status": "pending", "ts": None, "detail": ""} for t in tiers},
    }


def cmd_start(argv: list[str]) -> None:
    if not argv:
        sys.exit("start: falta <pipeline>")
    pipeline = argv[0]
    ttl = DEFAULT_TTL
    if "--ttl" in argv:
        ttl = int(argv[argv.index("--ttl") + 1])
    tiers = PIPELINES.get(pipeline)
    if tiers is None:
        sys.exit(f"start: pipeline desconocido '{pipeline}' (esperaba {list(PIPELINES)})")

    existing = _load(pipeline)
    resumed = False
    if (
        existing
        and not existing.get("finished")
        and (time.time() - existing.get("started_epoch", 0)) <= ttl
    ):
        data = existing
        # Asegurá que estén todos los tiers esperados (por si cambió la lista).
        for t in tiers:
            data["tiers"].setdefault(t, {"status": "pending", "ts": None, "detail": ""})
        resumed = True
    else:
        data = _new_checkpoint(pipeline, tiers)

    _save(pipeline, data)

    skip = [t for t in tiers if data["tiers"].get(t, {}).get("status") in RESOLVED]
    pending = [t for t in tiers if t not in skip]
    print(json.dumps({
        "pipeline": pipeline,
        "run_id": data["run_id"],
        "resumed": resumed,
        "skip": skip,
        "pending": pending,
    }, ensure_ascii=False))


def cmd_mark(argv: list[str]) -> None:
    if len(argv) < 3:
        sys.exit("mark: uso: mark <pipeline> <tier> <status> [detalle...]")
    pipeline, tier, status = argv[0], argv[1], argv[2]
    detail = " ".join(argv[3:])
    if status not in EMOJI:
        sys.exit(f"mark: status inválido '{status}' (esperaba {sorted(set(EMOJI) - {'pending'})})")
    data = _load(pipeline)
    if data is None:
        sys.exit(f"mark: no hay checkpoint activo para '{pipeline}' (corré `start {pipeline}` primero)")
    data["tiers"][tier] = {"status": status, "ts": _now_iso(), "detail": detail}
    _save(pipeline, data)
    print(f"{EMOJI[status]} {tier}: {status}" + (f" — {detail}" if detail else ""))


def cmd_done(argv: list[str]) -> None:
    if not argv:
        sys.exit("done: falta <pipeline>")
    pipeline = argv[0]
    data = _load(pipeline)
    if data is None:
        sys.exit(f"done: no hay checkpoint activo para '{pipeline}'")
    data["finished"] = True
    data["finished_at"] = _now_iso()
    _save(pipeline, data)
    print("checkpoint marcado como terminado")


def cmd_reopen(argv: list[str]) -> None:
    if not argv:
        sys.exit("reopen: falta <pipeline>")
    pipeline = argv[0]
    data = _load(pipeline)
    if data is None:
        print(json.dumps({"reopened": False, "reason": f"sin checkpoint para '{pipeline}'"}))
        sys.exit(1)
    order = PIPELINES.get(pipeline, list(data.get("tiers", {})))
    deferred = [t for t in order if data["tiers"].get(t, {}).get("status") == "deferred"]
    if not deferred:
        print(json.dumps({"reopened": False, "reason": "ningún tier diferido"}))
        sys.exit(1)
    first = order.index(deferred[0])
    reset = order[first:]
    for t in reset:
        data["tiers"][t] = {"status": "pending", "ts": None, "detail": ""}
    data["finished"] = False
    data["started_epoch"] = time.time()  # refresca la ventana de resume: la corrida sigue ahora
    data["reopened_at"] = _now_iso()
    data["reopen_count"] = data.get("reopen_count", 0) + 1
    _save(pipeline, data)
    print(json.dumps({"reopened": True, "from": deferred[0], "deferred": deferred,
                      "reset": reset, "reopen_count": data["reopen_count"]}, ensure_ascii=False))


def cmd_summary(argv: list[str]) -> None:
    if not argv:
        sys.exit("summary: falta <pipeline>")
    pipeline = argv[0]
    fmt = "md"
    if "--format" in argv:
        fmt = argv[argv.index("--format") + 1]
    data = _load(pipeline)
    if data is None:
        sys.exit(f"summary: no hay checkpoint para '{pipeline}'")
    if fmt == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    tiers = data.get("tiers", {})
    order = PIPELINES.get(data.get("pipeline"), list(tiers))
    counts: dict[str, int] = {}
    lines = [f"### Pipeline `{data.get('pipeline')}` — run {data.get('run_id')}", ""]
    lines.append("| Tier | Estado | Detalle |")
    lines.append("|---|---|---|")
    for t in order:
        info = tiers.get(t, {"status": "pending", "detail": ""})
        st = info.get("status", "pending")
        counts[st] = counts.get(st, 0) + 1
        lines.append(f"| {t} | {EMOJI.get(st, '?')} {st} | {info.get('detail', '') or '—'} |")
    roll = ", ".join(f"{EMOJI.get(k, '')} {v} {k}" for k, v in sorted(counts.items()))
    lines.append("")
    lines.append(f"**Resumen:** {roll}")
    print("\n".join(lines))


def cmd_show(argv: list[str]) -> None:
    if not argv:
        sys.exit("show: falta <pipeline>")
    data = _load(argv[0])
    print(json.dumps(data, indent=2, ensure_ascii=False) if data else "(sin checkpoint)")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, rest = sys.argv[1], sys.argv[2:]
    handlers = {
        "start": cmd_start,
        "mark": cmd_mark,
        "done": cmd_done,
        "reopen": cmd_reopen,
        "summary": cmd_summary,
        "show": cmd_show,
    }
    handler = handlers.get(cmd)
    if handler is None:
        sys.exit(f"comando desconocido '{cmd}' (esperaba {list(handlers)})")
    handler(rest)


if __name__ == "__main__":
    main()
