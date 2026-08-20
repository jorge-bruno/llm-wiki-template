#!/usr/bin/env python3
"""
pipeline_preflight.py — chequeo de entorno previo a una corrida del pipeline (refresh / pipeline-diario).

Verifica lo que se puede verificar de forma determinística desde el shell, ANTES de gastar una
sesión `claude -p` descubriendo que una fuente está rota:
  - `gh`: resoluble en el PATH + autenticado (tier GitHub).
  - red: conectividad TCP a github.com:443 (cubre `gh` y `git push`).
  - MCP: `claude mcp list` reporta el health de cada server, incluidos los conectores de claude.ai
    (Slack, Calendar, Atlassian) y los locales (Granola) → `✔ Connected` vs `! Needs authentication`.

Sobre los MCP: el health del shell dice si el conector está **sano a nivel cuenta**, no si quedó
**enumerado en la sesión** `claude -p` que corre el pipeline (son cosas distintas: hay corridas donde
Granola se enumera y los conectores de claude.ai no). Por eso cada tier de MCP sigue siendo
"probe-required" para el agente, pero con una regla nueva: si acá figura `connected` y el `ToolSearch`
del agente no encuentra el tool, eso NO es "MCP no disponible" — es enumeración fallida de esa sesión, y
el tier va `deferred` (se reintenta en sesión nueva), nunca `skipped`. Ver la SKILL del pipeline.

Salida (stdout): JSON con el estado de cada chequeo + una recomendación de qué tiers saltear.
Código de salida: siempre 0 (preflight informa, no aborta — el pipeline decide).
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# MCP que usa el pipeline. El shell chequea su health; el agente sondea la enumeración en su sesión.
MCP_TIERS = ["granola", "slack", "calendar", "atlassian"]

# Nombre del server en `claude mcp list` → tier del pipeline.
MCP_SERVER_TO_TIER = {
    "granola": "granola",
    "claude.ai Slack": "slack",
    "claude.ai Google Calendar": "calendar",
    "claude.ai Atlassian": "atlassian",
}

# `claude mcp list` imprime: "<nombre>: <url> [(HTTP)] - <estado>"
_MCP_LINE = re.compile(r"^(?P<name>.+?): (?P<url>\S+)(?: \([^)]+\))? - (?P<status>.+)$")


def _resolve_bin(name: str, extra: tuple = ()) -> "str | None":
    """Ruta absoluta a un binario. El launchd corre el pipeline con un PATH mínimo que no incluye
    homebrew (`/opt/homebrew/bin`) ni `~/.local/bin`, así que `shutil.which` devuelve None en el cron
    aunque el binario ande interactivo. Mismo patrón que extract_github_prs.py y node/nvm."""
    found = shutil.which(name)
    if found:
        return found
    for cand in extra:
        if os.path.exists(cand):
            return cand
    return None


def _resolve_gh() -> "str | None":
    return _resolve_bin("gh", ("/opt/homebrew/bin/gh", "/usr/local/bin/gh", "/usr/bin/gh"))


def check_gh() -> dict:
    """gh resoluble (PATH o paths conocidos de homebrew) + autenticado."""
    path = _resolve_gh()
    if not path:
        return {"ok": False, "found": False, "authenticated": False,
                "reason": "gh no está instalado (ni en el PATH ni en los paths conocidos)"}
    try:
        res = subprocess.run([path, "auth", "status"], capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "found": True, "path": path, "authenticated": False,
                "reason": f"`gh auth status` falló: {e}"}
    authed = res.returncode == 0
    return {
        "ok": authed,
        "found": True,
        "path": path,
        "authenticated": authed,
        "reason": "OK" if authed else "gh no autenticado (`gh auth login`)",
    }


def check_network(host: str = "github.com", port: int = 443, timeout: float = 5.0) -> dict:
    """Conectividad TCP — cubre `gh` y `git push`."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "host": host, "reason": "OK"}
    except OSError as e:
        return {"ok": False, "host": host, "reason": f"sin conexión a {host}:{port} ({e})"}


def check_mcp(timeout: float = 90.0) -> dict:
    """Health de los MCP server vía `claude mcp list` (incluye los conectores de claude.ai).

    Devuelve `{ok, reliable, servers: {tier: {connected, status, server}}, reason}`.

    `reliable` es lo importante: los conectores de claude.ai se listan consultando la cuenta, y eso
    necesita el token de auth (Keychain). En un entorno sin acceso a esa credencial —PATH/env recortado,
    o el CLI todavía no pudo autenticarse tras un wake— la salida degrada a los server locales y encima
    los muestra `! Needs authentication`. Si NO aparece ni un server `claude.ai *`, el chequeo no dice
    nada sobre el health real: `reliable=False`, `servers={}` y **cero recomendaciones de skip** (no
    poder chequear no es evidencia de que esté caído). Interpretarlo al revés saltearía Slack por una
    lectura errónea del shell, que es justo el bug que este chequeo viene a evitar.
    """
    path = _resolve_bin("claude", (str(Path.home() / ".local/bin/claude"), "/opt/homebrew/bin/claude"))
    if not path:
        return {"ok": False, "reliable": False, "servers": {},
                "reason": "el CLI `claude` no es resoluble desde el shell"}
    try:
        res = subprocess.run([path, "mcp", "list"], capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "reliable": False, "servers": {}, "reason": f"`claude mcp list` falló: {e}"}

    servers: dict[str, dict] = {}
    saw_connector = False
    for line in res.stdout.splitlines():
        m = _MCP_LINE.match(line.strip())
        if not m:
            continue
        name = m.group("name").strip()
        if name.startswith("claude.ai "):
            saw_connector = True
        tier = MCP_SERVER_TO_TIER.get(name)
        if not tier:
            continue
        status = m.group("status").strip()
        servers[tier] = {"connected": status.startswith("✔"), "status": status, "server": name}

    if not saw_connector:
        return {"ok": False, "reliable": False, "servers": {},
                "reason": "`claude mcp list` no listó los conectores de claude.ai (sin credencial de "
                          "cuenta en este entorno) → health desconocido, no saltear por esto"}
    down = [t for t, s in servers.items() if not s["connected"]]
    return {
        "ok": not down,
        "reliable": True,
        "servers": servers,
        "reason": "OK" if not down else f"sin conexión: {', '.join(sorted(down))}",
    }


def main() -> None:
    # `--require-mcp`: modo chequeo para los wrappers de launchd. Sale 0 si los conectores de claude.ai
    # son visibles desde el shell, 1 si no. Sirve para esperar a que la credencial de cuenta esté
    # disponible ANTES de lanzar la sesión: si arranca sin eso, la sesión no enumera Slack/Calendar/
    # Atlassian y esos tiers quedan diferidos al toque.
    if "--require-mcp" in sys.argv:
        mcp = check_mcp()
        print(mcp["reason"], file=sys.stderr)
        sys.exit(0 if mcp.get("reliable") else 1)

    gh = check_gh()
    network = check_network()
    mcp = check_mcp()

    skip: list[str] = []
    if not network["ok"]:
        skip += ["github", "backup"]  # ambos necesitan red
    if not gh["ok"]:
        skip.append("github")
    # Un conector sin auth no se arregla headless (el OAuth necesita browser) → skip legítimo.
    skip += [t for t, s in mcp["servers"].items() if not s["connected"]]

    # Tiers cuyo conector está sano: si el ToolSearch del agente no los encuentra, es enumeración
    # fallida de la sesión → `deferred` (reintento en sesión nueva), NO `skipped`.
    healthy = sorted(t for t, s in mcp["servers"].items() if s["connected"])

    out = {
        "checks": {"gh": gh, "network": network, "mcp": mcp},
        "mcp_probe_required": MCP_TIERS,
        "mcp_healthy_defer_if_missing": healthy,
        "recommend_skip": sorted(set(skip)),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

    # Resumen legible a stderr (para los logs de launchd).
    print("preflight:", file=sys.stderr)
    for name, c in out["checks"].items():
        flag = "✅" if c["ok"] else "⚠️"
        print(f"  {flag} {name}: {c['reason']}", file=sys.stderr)
    for tier, s in sorted(mcp["servers"].items()):
        print(f"      {'✔' if s['connected'] else '✘'} {tier}: {s['status']}", file=sys.stderr)
    if healthy:
        print(f"  MCP sanos (si el ToolSearch no los ve → deferred, NO skipped): {', '.join(healthy)}",
              file=sys.stderr)
    if out["recommend_skip"]:
        print(f"  → recomiendo saltear: {', '.join(out['recommend_skip'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
