"""Interaktivní protokol v jednom HTML souboru (otevře se v prohlížeči, jde poslat e-mailem).

Obsahuje přehledku výkresu s kroužky chyb (klik = výběr v seznamu), karty se souhrnem,
filtr podle závažnosti a skupiny, vyhledávání, návod k opravě a výřez výkresu u každé chyby.
Vše je uvnitř souboru (obrázky jako base64), nic se nenačítá z internetu.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
from html import escape
from pathlib import Path

from ..checks.base import REGISTRY, Issue, Severity
from ..navody import navod
from ..skore import compute_score

_COL = {Severity.CHYBA: "#DC2626", Severity.VAROVANI: "#D97706", Severity.INFO: "#2563EB"}


def export_html(issues: list[Issue], path: str | Path, drawing_name: str = "", project_name: str = "",
                overview: bytes | None = None, positions: dict[int, tuple[float, float]] | None = None,
                overview_size: tuple[int, int] | None = None, images: dict[int, bytes] | None = None,
                has_rules: bool = True, rozsah: str = "") -> Path:
    images = images or {}
    positions = positions or {}
    sk = compute_score(issues, has_rules)
    ilu: dict[str, str] = {}  # obrázek „chyba / správně“ jednou za typ chyby
    try:
        from ..ui.help_topics import illustration_svg
        for cid in {i.check_id for i in issues}:
            svg = illustration_svg(cid)
            if svg:
                ilu[cid] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()
    except ImportError:  # bez Qt (jen příkazová řádka) se obrázky vynechají
        ilu = {}
    rows = []
    for i in issues:
        rows.append({
            "n": i.number, "sev": i.severity.value, "col": _COL.get(i.severity, "#6B7280"),
            "grp": getattr(REGISTRY.get(i.check_id), "skupina", ""), "typ": i.check_name, "msg": i.message,
            "layer": i.layer, "x": round(i.x, 3), "y": round(i.y, 3), "state": i.state,
            "hint": navod(i) or "", "note": i.note, "cid": i.check_id,
            "img": ("data:image/png;base64," + base64.b64encode(images[i.number]).decode()) if i.number in images
            else "",
            "px": positions.get(i.number),
        })
    ov = ("data:image/png;base64," + base64.b64encode(overview).decode()) if overview else ""
    ow, oh = overview_size or (900, 600)
    open_ = [i for i in issues if i.state == "nová"]
    cnt = {s: sum(1 for i in open_ if i.severity == s) for s in Severity}
    now = dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    html = _TEMPLATE
    for k, v in {
        "__TITLE__": escape(f"Protokol kontroly – {drawing_name}"),
        "__ROZSAH__": (f'<div class="sub">{escape(rozsah)}</div>' if rozsah else ""),
        "__DRAWING__": escape(drawing_name or "–"), "__PROJECT__": escape(project_name or "–"), "__DATE__": now,
        "__SCORE__": str(sk.hodnota), "__SCORECOL__": sk.barva, "__SCORETXT__": escape(sk.popis),
        "__NCH__": str(cnt[Severity.CHYBA]), "__NVA__": str(cnt[Severity.VAROVANI]),
        "__NIN__": str(cnt[Severity.INFO]),
        "__TODO__": str(cnt[Severity.CHYBA] + cnt[Severity.VAROVANI]),
        "__OV__": ov, "__OW__": str(ow), "__OH__": str(oh),
        "__DATA__": json.dumps(rows, ensure_ascii=False).replace("</", "<\\/"),
        "__ILU__": json.dumps(ilu),
    }.items():
        html = html.replace(k, v)
    path = Path(path)
    path.write_text(html, encoding="utf-8")
    return path


_TEMPLATE = r"""<!doctype html>
<html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#F3F4F6;--panel:#fff;--text:#1F2937;--muted:#6B7280;--border:#E5E7EB;--accent:#2563EB;--soft:#EFF6FF}
@media (prefers-color-scheme:dark){:root{--bg:#1E1F22;--panel:#2B2D31;--text:#E5E7EB;--muted:#9CA3AF;
--border:#3A3D44;--accent:#60A5FA;--soft:#1E2A3D}}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",system-ui,Arial,sans-serif;background:var(--bg);
color:var(--text)}header{padding:20px 24px 8px}h1{margin:0;font-size:22px}.sub{color:var(--muted);font-size:13px}
.cards{display:flex;flex-wrap:wrap;gap:10px;padding:8px 24px}.card{background:var(--panel);border:1px solid var(--border);
border-radius:12px;padding:10px 16px;min-width:120px}.card b{font-size:24px;display:block}.card span{color:var(--muted);
font-size:12px}.score{display:flex;align-items:center;gap:12px}.ring{width:64px;height:64px;border-radius:50%;
display:grid;place-items:center;font-weight:800;font-size:20px;background:conic-gradient(__SCORECOL__ calc(__SCORE__*1%),
var(--border) 0)}.ring i{width:50px;height:50px;border-radius:50%;background:var(--panel);display:grid;place-items:center;
font-style:normal}main{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:14px;padding:10px 24px 24px}
@media (max-width:900px){main{grid-template-columns:1fr}}.box{background:var(--panel);border:1px solid var(--border);
border-radius:12px;padding:12px;min-width:0}.ovwrap{position:relative;width:100%}.ovwrap img{width:100%;display:block;
border-radius:8px}.ovwrap svg{position:absolute;inset:0;width:100%;height:100%}circle.m{fill:transparent;stroke-width:3;
cursor:pointer}circle.m.sel{stroke-width:6}.tools{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.tools button{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:14px;
padding:4px 12px;cursor:pointer}.tools button.on{background:var(--soft);border-color:var(--accent);color:var(--accent);
font-weight:600}.tools input{flex:1;min-width:160px;padding:6px 10px;border-radius:8px;border:1px solid var(--border);
background:var(--panel);color:var(--text)}.list{max-height:70vh;overflow:auto}.it{border-bottom:1px solid var(--border);
padding:8px 6px;cursor:pointer;display:grid;grid-template-columns:44px 1fr;gap:8px}.it:hover,.it.sel{background:var(--soft)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.n{color:var(--muted);font-size:12px}
.msg{font-weight:500;font-size:14px}.meta{color:var(--muted);font-size:12px}.hint{margin-top:6px;font-size:13px;background:var(--soft);
border-radius:8px;padding:6px 8px;display:none}.it.sel .hint{display:block}.hint img.ilu{max-width:220px;margin-top:6px;border-radius:6px;display:block}.it img{max-width:260px;border-radius:6px;
margin-top:6px;display:none}.it.sel img{display:block}.done{opacity:.55;text-decoration:line-through}
footer{color:var(--muted);font-size:12px;padding:0 24px 24px}
</style></head><body>
<header><h1>Protokol kontroly výkresu</h1>
<div class="sub">Výkres <b>__DRAWING__</b> · projekt __PROJECT__ · __DATE__</div>__ROZSAH__</header>
<div class="cards">
 <div class="card score"><div class="ring"><i>__SCORE__</i></div><div><b style="font-size:15px;color:__SCORECOL__">__SCORETXT__</b>
 <span>připravenost k odevzdání (orientační)</span></div></div>
 <div class="card"><b>__TODO__</b><span>k opravě</span></div>
 <div class="card"><b style="color:#DC2626">__NCH__</b><span>chyby</span></div>
 <div class="card"><b style="color:#D97706">__NVA__</b><span>varování</span></div>
 <div class="card"><b style="color:#2563EB">__NIN__</b><span>info</span></div>
</div>
<main>
 <div class="box"><div class="ovwrap" id="ov"><img src="__OV__" alt="Přehledka výkresu">
 <svg viewBox="0 0 __OW__ __OH__" preserveAspectRatio="none" id="marks"></svg></div>
 <div class="meta" style="margin-top:6px">Klikněte na kroužek – v seznamu se ukáže chyba s návodem.</div></div>
 <div class="box"><div class="tools" id="f">
  <button data-f="all" class="on">Vše</button><button data-f="todo">K opravě</button>
  <button data-f="Topologie">Topologie</button><button data-f="Atributy">Atributy</button>
  <input id="q" placeholder="Hledat (vrstva, text, číslo)…"></div>
  <div class="list" id="list"></div></div>
</main>
<footer>Vytvořeno aplikací Kontrola výkresu. Souřadnice jsou v S-JTSK (jako ve výkresu).</footer>
<script>
const D=__DATA__;const ILU=__ILU__;let F="all",Q="",SEL=null;
const list=document.getElementById("list"),marks=document.getElementById("marks");
function esc(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function ok(r){if(F==="todo"&&(r.state!=="nová"||r.sev==="info"))return false;if(F!=="all"&&F!=="todo"&&r.grp!==F)return false;
 if(Q&&!(r.msg+" "+r.layer+" "+r.typ+" "+r.n).toLowerCase().includes(Q))return false;return true}
function render(){list.innerHTML="";marks.innerHTML="";const ns="http://www.w3.org/2000/svg";
 D.filter(ok).forEach(r=>{const el=document.createElement("div");el.className="it"+(SEL===r.n?" sel":"");el.id="i"+r.n;
  el.innerHTML=`<div class="n">#${r.n}</div><div><div class="msg ${r.state!=="nová"?"done":""}"><span class="dot" style="background:${r.col}"></span>${esc(r.msg)}</div>
  <div class="meta">${esc(r.typ)} · vrstva ${esc(r.layer||"–")} · Y ${r.x} · X ${r.y}${r.state!=="nová"?" · "+esc(r.state):""}</div>
  ${r.hint?`<div class="hint"><b>Jak opravit:</b> ${esc(r.hint)}${ILU[r.cid]?`<br><img class="ilu" src="${ILU[r.cid]}" alt="chyba / správně">`:""}</div>`:""}${r.img?`<img src="${r.img}" alt="">`:""}</div>`;
  el.onclick=()=>select(r.n,false);list.appendChild(el);
  if(r.px){const c=document.createElementNS(ns,"circle");c.setAttribute("cx",r.px[0]);c.setAttribute("cy",r.px[1]);
   c.setAttribute("r",SEL===r.n?14:10);c.setAttribute("class","m"+(SEL===r.n?" sel":""));c.setAttribute("stroke",r.col);
   const t=document.createElementNS(ns,"title");t.textContent="#"+r.n+" "+r.msg;c.appendChild(t);
   c.onclick=()=>select(r.n,true);marks.appendChild(c)}})}
function select(n,scroll){SEL=SEL===n&&!scroll?null:n;render();if(scroll){const e=document.getElementById("i"+n);if(e)e.scrollIntoView({block:"center"})}}
document.querySelectorAll("#f button").forEach(b=>b.onclick=()=>{F=b.dataset.f;document.querySelectorAll("#f button").forEach(x=>x.classList.toggle("on",x===b));render()});
document.getElementById("q").oninput=e=>{Q=e.target.value.toLowerCase();render()};
render();
</script></body></html>
"""
