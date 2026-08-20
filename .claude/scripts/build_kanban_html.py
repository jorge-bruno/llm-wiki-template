#!/usr/bin/env python3
"""
build_kanban_html.py — Kanban board de TODOs como HTML con drag & drop.

Lee todos/*.md, parsea frontmatter, genera kanban.html auto-contenido. El drag & drop
actualiza estado: en el frontmatter via require('fs') (node-integration Electron/Obsidian).
Lo regenera /todos tras crear/patchear TODOs y /compactar diario tras sync Jira.

Uso: python3 build_kanban_html.py
"""
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

VAULT = Path(__file__).resolve().parent.parent.parent
OUT = VAULT / "kanban.html"
TODOS_DIR = VAULT / "todos"
COLUMNS = ["pendiente", "en-progreso", "hecho", "descartado"]


def vault_ref() -> str:
    cfg = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        for vid, v in data.get("vaults", {}).items():
            if Path(v.get("path", "")) == VAULT:
                return vid
    except Exception:
        pass
    return VAULT.name


def parse_todo(path: Path) -> Optional[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return None
    fm, body = m.group(1), m.group(2)

    def val(key: str) -> str:
        r = re.search(rf"^{key}:\s*(.+?)\s*$", fm, re.MULTILINE)
        return r.group(1) if r else ""

    estado = val("estado")
    if estado not in COLUMNS:
        return None
    title_m = re.search(r"^# (.+)$", body, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else path.stem.replace("-", " ")
    return {
        "slug": path.stem,
        "title": title,
        "estado": estado,
        "proyecto": val("proyecto"),
        "due": val("due"),
    }


def main() -> int:
    todos = [t for p in sorted(TODOS_DIR.glob("*.md")) if (t := parse_todo(p)) is not None]
    counts = {c: sum(1 for t in todos if t["estado"] == c) for c in COLUMNS}
    html = (TEMPLATE
            .replace("/*__TODOS__*/", json.dumps(todos, ensure_ascii=False))
            .replace("__VAULT__", vault_ref())
            .replace("__VAULT_PATH__", str(VAULT))
            .replace("__GENERATED__", date.today().isoformat()))
    OUT.write_text(html, encoding="utf-8")
    print(f"kanban.html generado: {OUT}  "
          f"(pendiente={counts['pendiente']}, "
          f"en-progreso={counts['en-progreso']}, "
          f"hecho={counts['hecho']}, "
          f"descartado={counts['descartado']})")
    return 0


TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Kanban — TODOs</title>
<style>
  :root {
    --bg: #11131a; --panel: #171a23; --ink: #e6e8ef; --muted: #8b90a3;
    --border: #232733; --card-bg: #1e2130; --card-border: #2b3142; --card-hover: #252840;
    --pendiente: #f5a97f; --en-progreso: #8aadf4; --hecho: #a6da95; --descartado: #6e738d;
    --overdue: #ed8796; --soon: #eed49f;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; overflow: hidden; background: var(--bg); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { display: flex; flex-direction: column; }

  header { flex: 0 0 auto; display: flex; align-items: center; gap: 14px;
    padding: 10px 16px; border-bottom: 1px solid var(--border); background: var(--panel); }
  header h1 { font-size: 14px; font-weight: 600; }
  .ts { font-size: 11px; color: var(--muted); }
  .hint { font-size: 11px; color: var(--muted); margin-left: auto; }

  .board { flex: 1 1 auto; width: 100%; min-height: 0; display: flex; gap: 12px; padding: 14px;
    overflow-x: auto; align-items: flex-start; }

  .col { flex: 1 1 290px; display: flex; flex-direction: column; background: var(--panel);
    border-radius: 10px; border: 1px solid var(--border);
    max-height: calc(100vh - 76px); transition: border-color 0.15s, background 0.15s; }
  .col.drag-over { border-color: var(--en-progreso); background: rgba(138,173,244,0.06); }
  .col.collapsed { max-height: none; }

  .col-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px;
    border-bottom: 1px solid var(--border); cursor: pointer; user-select: none;
    border-radius: 10px 10px 0 0; }
  .col.collapsed .col-header { border-bottom: none; border-radius: 10px; }
  .col-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .col-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; }
  .col-count { font-size: 11px; color: var(--muted); background: #252840;
    border-radius: 10px; padding: 1px 7px; margin-left: auto; }
  .col-toggle { font-size: 10px; color: var(--muted); }

  .cards { flex: 1 1 auto; overflow-y: auto; padding: 8px; display: flex;
    flex-direction: column; gap: 6px; min-height: 40px; }
  .col.collapsed .cards { display: none; }

  .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 7px;
    padding: 9px 11px; cursor: grab; transition: background 0.1s, border-color 0.1s, opacity 0.15s; }
  .card:hover { background: var(--card-hover); border-color: #3a4259; }
  .card:active { cursor: grabbing; }
  .card.dragging { opacity: 0.35; }

  .card-title { font-size: 12.5px; font-weight: 500; line-height: 1.45;
    margin-bottom: 6px; color: var(--ink); }
  .card-meta { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: #252840;
    color: var(--muted); white-space: nowrap; max-width: 150px;
    overflow: hidden; text-overflow: ellipsis; }
  .due { font-size: 10px; padding: 2px 6px; border-radius: 4px;
    color: var(--muted); background: #252840; }
  .due.overdue { color: var(--overdue); background: rgba(237,135,150,0.13); }
  .due.soon    { color: var(--soon);    background: rgba(238,212,159,0.13); }

  .cards::-webkit-scrollbar { width: 4px; }
  .cards::-webkit-scrollbar-track { background: transparent; }
  .cards::-webkit-scrollbar-thumb { background: #313748; border-radius: 4px; }
</style>
</head>
<body>
<header>
  <h1>Kanban · TODOs</h1>
  <span class="ts">generado __GENERATED__</span>
  <span class="hint">drag para mover estado · click para abrir en Obsidian</span>
</header>
<div class="board">
  <div class="col" id="col-pendiente" data-estado="pendiente">
    <div class="col-header" onclick="toggleCol('pendiente')">
      <span class="col-dot" style="background:var(--pendiente)"></span>
      <span class="col-title">pendiente</span>
      <span class="col-count" id="count-pendiente">0</span>
    </div>
    <div class="cards" id="cards-pendiente"></div>
  </div>
  <div class="col" id="col-en-progreso" data-estado="en-progreso">
    <div class="col-header" onclick="toggleCol('en-progreso')">
      <span class="col-dot" style="background:var(--en-progreso)"></span>
      <span class="col-title">en progreso</span>
      <span class="col-count" id="count-en-progreso">0</span>
    </div>
    <div class="cards" id="cards-en-progreso"></div>
  </div>
  <div class="col collapsed" id="col-hecho" data-estado="hecho">
    <div class="col-header" onclick="toggleCol('hecho')">
      <span class="col-dot" style="background:var(--hecho)"></span>
      <span class="col-title">hecho</span>
      <span class="col-count" id="count-hecho">0</span>
      <span class="col-toggle" id="toggle-hecho">▶</span>
    </div>
    <div class="cards" id="cards-hecho"></div>
  </div>
  <div class="col collapsed" id="col-descartado" data-estado="descartado">
    <div class="col-header" onclick="toggleCol('descartado')">
      <span class="col-dot" style="background:var(--descartado)"></span>
      <span class="col-title">descartado</span>
      <span class="col-count" id="count-descartado">0</span>
      <span class="col-toggle" id="toggle-descartado">▶</span>
    </div>
    <div class="cards" id="cards-descartado"></div>
  </div>
</div>
<script>
const TODOS = /*__TODOS__*/;
const VAULT = '__VAULT__';
const VAULT_PATH = '__VAULT_PATH__';

function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function dueClass(due){
  if(!due) return '';
  const today=new Date(); today.setHours(0,0,0,0);
  const diff=(new Date(due+'T00:00:00')-today)/86400000;
  return diff<0?'overdue':diff<=3?'soon':'';
}
function formatDue(due){
  if(!due) return '';
  return new Date(due+'T00:00:00').toLocaleDateString('es-AR',{day:'numeric',month:'short'});
}

async function writeEstado(slug, estado){
  const rel='todos/'+slug+'.md';
  const patch=c=>c.replace(/^estado: .*$/m,'estado: '+estado);
  // 1) API de Obsidian: el iframe del plugin embed-html es same-origin pero carga desde
  //    blob: (sin node-integration), así que require('fs') no existe. vault.process hace
  //    el read-modify-write atomico y persiste a disco.
  try{
    const app=window.top&&window.top.app;
    if(app&&app.vault){
      const f=app.vault.getAbstractFileByPath(rel);
      if(f){
        if(app.vault.process) await app.vault.process(f,patch);
        else await app.vault.modify(f,patch(await app.vault.read(f)));
        return true;
      }
    }
  }catch(e){ console.error('[kanban] vault write fail',e); }
  // 2) Fallback: HTML abierto standalone con node-integration.
  try{
    const fs=require('fs'), path=require('path');
    const file=path.join(VAULT_PATH,'todos',slug+'.md');
    fs.writeFileSync(file,patch(fs.readFileSync(file,'utf-8')),'utf-8');
    return true;
  }catch(e){}
  return false;
}

function makeCard(t){
  const div=document.createElement('div');
  div.className='card'; div.draggable=true; div.dataset.slug=t.slug;
  const meta=[];
  if(t.proyecto) meta.push('<span class="badge">'+esc(t.proyecto)+'</span>');
  if(t.due) meta.push('<span class="due '+dueClass(t.due)+'">'+esc(formatDue(t.due))+'</span>');
  div.innerHTML='<div class="card-title">'+esc(t.title)+'</div>'
    +(meta.length?'<div class="card-meta">'+meta.join('')+'</div>':'');
  div.addEventListener('dragstart',e=>{
    e.dataTransfer.setData('text/plain',t.slug);
    div.classList.add('dragging');
  });
  div.addEventListener('dragend',()=>div.classList.remove('dragging'));
  div.addEventListener('click',()=>{
    window.open('obsidian://open?vault='+encodeURIComponent(VAULT)
      +'&file='+encodeURIComponent('todos/'+t.slug+'.md'),'_blank');
  });
  return div;
}

function render(){
  ['pendiente','en-progreso','hecho','descartado'].forEach(col=>{
    const items=TODOS.filter(t=>t.estado===col);
    const container=document.getElementById('cards-'+col);
    container.innerHTML='';
    items.forEach(t=>container.appendChild(makeCard(t)));
    document.getElementById('count-'+col).textContent=items.length;
  });
}

// El JSON embebido queda stale apenas se mueve una card (kanban.html no se regenera en
// el drag). Los .md son la fuente de verdad: al cargar, releemos su estado real via la
// API de Obsidian para que la vista nunca muestre un estado desactualizado.
async function syncFromDisk(){
  try{
    const app=window.top&&window.top.app;
    if(!app||!app.vault) return;   // standalone sin Obsidian: usar el JSON embebido
    await Promise.all(TODOS.map(async t=>{
      const f=app.vault.getAbstractFileByPath('todos/'+t.slug+'.md');
      if(!f) return;
      const m=(await app.vault.cachedRead(f)).match(/^estado:\s*(.+?)\s*$/m);
      if(m && ['pendiente','en-progreso','hecho','descartado'].includes(m[1])) t.estado=m[1];
    }));
  }catch(e){ console.error('[kanban] sync fail',e); }
}

function toggleCol(id){
  const col=document.getElementById('col-'+id);
  col.classList.toggle('collapsed');
  const tog=document.getElementById('toggle-'+id);
  if(tog) tog.textContent=col.classList.contains('collapsed')?'▶':'▼';
}

function flashError(){
  let t=document.getElementById('kanban-err');
  if(!t){
    t=document.createElement('div'); t.id='kanban-err';
    t.style.cssText='position:fixed;bottom:14px;left:50%;transform:translateX(-50%);'
      +'background:rgba(237,135,150,0.15);border:1px solid var(--overdue);color:var(--overdue);'
      +'padding:8px 14px;border-radius:6px;font-size:12px;z-index:99;transition:opacity .3s;';
    document.body.appendChild(t);
  }
  t.textContent='⚠ no se pudo guardar el estado en disco';
  t.style.opacity='1';
  clearTimeout(t._h); t._h=setTimeout(()=>{t.style.opacity='0';},2600);
}

document.querySelectorAll('.col').forEach(col=>{
  col.addEventListener('dragover',e=>{e.preventDefault(); col.classList.add('drag-over');});
  col.addEventListener('dragleave',e=>{
    if(!e.relatedTarget||!col.contains(e.relatedTarget)) col.classList.remove('drag-over');
  });
  col.addEventListener('drop',async e=>{
    e.preventDefault(); col.classList.remove('drag-over');
    const slug=e.dataTransfer.getData('text/plain');
    const newEstado=col.dataset.estado;
    const todo=TODOS.find(t=>t.slug===slug);
    if(todo && todo.estado!==newEstado){
      const prev=todo.estado;
      todo.estado=newEstado;
      const dest=document.getElementById('col-'+newEstado);
      if(dest && dest.classList.contains('collapsed')) toggleCol(newEstado);
      render();
      const ok=await writeEstado(slug,newEstado);
      if(!ok){ todo.estado=prev; render(); flashError(); }   // no persistio: revertir y avisar
    }
  });
});

render();
syncFromDisk().then(render);   // reconcilia con los .md (fuente de verdad) apenas carga

// Iframe height fix
try{
  const fe=window.frameElement;
  if(fe){
    const view=fe.closest('.view-content');
    if(view){
      let el=fe;
      while(el&&el!==view){el.style.height='100%';el.style.maxHeight='none';el=el.parentElement;}
      view.style.height='100%';
    }else{
      fe.style.height='100%';
      const c=fe.parentElement;
      if(c){c.style.height='90vh';c.style.maxHeight='none';}
    }
  }
}catch(e){}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
