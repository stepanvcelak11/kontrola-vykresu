// Webová verze – nástroje kontroly: záložky panelu (hladiny, prvek, změny), exporty protokolů, automatická oprava,
// porovnání se starší verzí, s protokolem učitele, předpověď a nastavení kontroly. Vše počítá Python ve workeru.
"use strict";

const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------------------------------------------------------------- dialog
function dialog(nadpis, html, tlacitka = []) {
  const d = $("dlg");
  $("dlg_nadpis").textContent = nadpis;
  $("dlg_telo").innerHTML = html;
  const t = $("dlg_tlacitka");
  t.innerHTML = "";
  for (const [text, fn, primarni] of [...tlacitka, ["Zavřít", () => d.close()]]) {
    const b = document.createElement("button");
    b.className = "tlacitko" + (primarni ? " primarni" : "");
    b.textContent = text;
    b.addEventListener("click", fn);
    t.appendChild(b);
  }
  if (!d.open) d.showModal();
  return d;
}
$("dlg_zavrit").addEventListener("click", () => $("dlg").close());
function chybaDialog(e) { dialog("Nepovedlo se", `<p>${esc(e.message || e)}</p>`); }
function vyberSoubor(accept) {
  return new Promise((ok) => {
    const i = document.createElement("input");
    i.type = "file"; i.accept = accept;
    i.addEventListener("change", async () => ok(i.files[0] ? await nacti(i.files[0]) : null));
    i.click();
  });
}

// ---------------------------------------------------------------- záložky panelu
function prepniPanel(z) {
  stav.panel = z;
  document.querySelectorAll(".zalozka").forEach((b) => b.classList.toggle("aktivni", b.dataset.z === z));
  for (const n of ["chyby", "hladiny", "prvek", "zmeny"]) $("z_" + n).classList.toggle("skryte", n !== z);
  prekresli();
}
document.querySelectorAll(".zalozka").forEach((b) => b.addEventListener("click", () => prepniPanel(b.dataset.z)));

// ---------------------------------------------------------------- hladiny (zapnout / vypnout jako v MicroStationu)
function barvaHladiny(n) {
  const k = stav.vysledek.kresba;
  const c = k.cary.find((x) => x.l === n) || k.texty.find((x) => x.l === n);
  if (c) return c.c;
  const b = k.body.find((x) => x[4] === n);
  return b ? b[2] : "#888";
}
function vykresliHladiny() {
  const v = stav.vysledek;
  const el = $("h_seznam");
  el.innerHTML = "";
  if (!v || !v.vrstvy) return;
  const t = ($("h_hledat").value || "").toLowerCase();
  for (const h of v.vrstvy) {
    if (t && !h.nazev.toLowerCase().includes(t)) continue;
    const r = document.createElement("label");
    r.className = "hladina";
    r.innerHTML = `<input type="checkbox" ${stav.skryteVrstvy.has(h.nazev) ? "" : "checked"}><span class="vzorek" style="background:${esc(barvaHladiny(h.nazev))}"></span><span class="nazev-h" title="${esc(h.nazev)}">${esc(h.nazev)}</span><span class="pocet">${h.prvku}</span>`;
    r.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) stav.skryteVrstvy.delete(h.nazev); else stav.skryteVrstvy.add(h.nazev);
      prekresli();
    });
    el.appendChild(r);
  }
}
$("h_hledat").addEventListener("input", vykresliHladiny);
$("h_vse").addEventListener("click", () => { stav.skryteVrstvy.clear(); vykresliHladiny(); prekresli(); });
$("h_nic").addEventListener("click", () => { for (const h of stav.vysledek ? stav.vysledek.vrstvy : []) stav.skryteVrstvy.add(h.nazev); vykresliHladiny(); prekresli(); });

// ---------------------------------------------------------------- inspektor prvku
async function inspektor(px, py) {
  if (!stav.vysledek || !stav.pripraveno) return;
  const tol = Math.max(8 / pohled.k, 0.05);
  try {
    const r = JSON.parse(await volej("prvek_na", [pohled.wx(px), pohled.wy(py), tol]));
    if (!r.vlastnosti) { stav.obrys = null; $("p_obsah").innerHTML = '<div class="prazdne">V místě kliknutí není žádný prvek.</div>'; prekresli(); return; }
    stav.obrys = r.obrys && r.obrys.length ? r.obrys : null;
    let h = '<table class="vlastnosti">' + Object.entries(r.vlastnosti).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("") + "</table>";
    if (r.chyby.length) h += '<div class="karta-nadpis" style="margin-top:14px">Chyby prvku</div>' + r.chyby.map((c) => `<div class="chyba-zprava">• ${esc(c)}</div>`).join("");
    $("p_obsah").className = "";
    $("p_obsah").innerHTML = h;
    if (stav.panel !== "prvek") prepniPanel("prvek"); else prekresli();
  } catch (e) { chybaDialog(e); }
}

// ---------------------------------------------------------------- menu Nástroje
$("b_nastroje").addEventListener("click", (e) => { e.stopPropagation(); $("m_nastroje").classList.toggle("skryte"); });
document.addEventListener("click", () => $("m_nastroje").classList.add("skryte"));
$("m_nastroje").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  $("m_nastroje").classList.add("skryte");
  if (b.dataset.export) return exportuj(b.dataset.export, b.textContent);
  ({ oprava: dlgOprava, porovnani: dlgPorovnani, ucitel: dlgUcitel, predikce: dlgPredikce })[b.dataset.nastroj]();
});

async function exportuj(druh, popis) {
  ukazStav("Připravuji: " + popis + "…");
  try {
    const { json, data } = await volejSoubor("export", [druh]);
    skryjStav();
    if (!data) throw new Error("Soubor se nepodařilo vytvořit.");
    stahniData(data, json.nazev);
  } catch (e) { skryjStav(); chybaDialog(e); }
}

// ---------------------------------------------------------------- automatická oprava
async function dlgOprava() {
  let volby;
  try { volby = JSON.parse(await volej("volby_opravy")); } catch (e) { return chybaDialog(e); }
  const html = '<p class="tlumene">Opraví, co jde opravit bez rozmýšlení (jako Oprava na desktopu). Vznikne nový výkres DXF – původní soubor zůstane, jak byl.</p>' +
    volby.map((v) => `<label class="volba"><input type="checkbox" data-v="${v.id}" ${v.zapnuto ? "checked" : ""}> ${esc(v.popis)}</label>`).join("");
  dialog("Automatická oprava", html, [["Opravit a stáhnout DXF", async () => {
    const o = {};
    document.querySelectorAll("#dlg_telo [data-v]").forEach((i) => { o[i.dataset.v] = i.checked; });
    ukazStav("Opravuji výkres…");
    try {
      const { json, data } = await volejSoubor("oprava", [JSON.stringify(o)]);
      skryjStav();
      stahniData(data, json.nazev);
      dialog("Automatická oprava – hotovo", `<pre>${esc(json.text)}</pre>` +
        (json.podrobne.length ? `<details><summary>Podrobně (${json.podrobne.length})</summary><pre>${esc(json.podrobne.join("\n"))}</pre></details>` : "") +
        (json.rucne.length ? `<details open><summary>Opravte ručně (${json.rucne.length})</summary><pre>${esc(json.rucne.join("\n"))}</pre></details>` : "") +
        '<p class="tlumene">Opravený výkres se stáhl. Otevřete ho tlačítkem Otevřít výkres a zkontrolujte znovu.</p>');
    } catch (e) { skryjStav(); chybaDialog(e); }
  }, true]]);
}

// ---------------------------------------------------------------- porovnání se starší verzí
async function dlgPorovnani() {
  const f = await vyberSoubor(".dxf,.dgn");
  if (!f) return;
  ukazStav("Porovnávám výkresy…");
  try {
    const r = JSON.parse(await volej("porovnej", [], f));
    skryjStav();
    stav.znacky = r.zmeny;
    $("zm_souhrn").textContent = `Proti ${f.nazev}: ${r.souhrn || "beze změn"}`;
    const sez = $("zm_seznam");
    sez.innerHTML = r.zmeny.length ? "" : '<div class="prazdne">Výkresy se neliší.</div>';
    for (const z of r.zmeny.slice(0, 1500)) {
      const b = document.createElement("button");
      b.className = "chyba-karta";
      const barva = z.druh.startsWith("přid") ? "info" : z.druh.startsWith("odeb") ? "chyba" : "varování";
      b.innerHTML = `<div class="chyba-hlava"><span class="tecka ${barva}"></span><span class="chyba-nazev">${esc(z.druh)}</span><span class="chyba-vrstva">${esc(z.vrstva)}</span></div><div class="chyba-zprava">${esc(z.popis)}</div>`;
      b.addEventListener("click", () => { stav.vybranaZnacka = z; document.querySelectorAll("#zm_seznam .chyba-karta").forEach((x) => x.classList.toggle("vybrana", x === b)); pohled.na(z.x, z.y); });
      z.karta = b;
      sez.appendChild(b);
    }
    document.querySelector(".zalozka[data-z=zmeny]").classList.remove("skryte");
    prepniPanel("zmeny");
  } catch (e) { skryjStav(); chybaDialog(e); }
}
function vyberZmenuNa(px, py) {
  let nej = null, d = 22;
  for (const z of stav.znacky) {
    const dd = Math.hypot(pohled.sx(z.x) - px, pohled.sy(z.y) - py);
    if (dd < d) { d = dd; nej = z; }
  }
  if (!nej) return;
  stav.vybranaZnacka = nej;
  document.querySelectorAll("#zm_seznam .chyba-karta").forEach((x) => x.classList.toggle("vybrana", x === nej.karta));
  if (nej.karta) nej.karta.scrollIntoView({ block: "nearest", behavior: "smooth" });
  prekresli();
}

// ---------------------------------------------------------------- protokol od učitele a předpověď
async function dlgUcitel() {
  const f = await vyberSoubor(".log,.txt");
  if (!f) return;
  try {
    const r = JSON.parse(await volej("protokol_ucitele", [], f));
    const radky = r.radky.map((x) => `<tr><td>${esc(x.vrstva)}</td><td>${esc(x.co)}</td><td class="cislo">${x.ucitel}</td><td class="cislo">${x.program}</td></tr>`).join("");
    dialog("Porovnání s protokolem od učitele", `<p>${esc(r.souhrn)}</p>` +
      (radky ? `<table><thead><tr><th>Hladina</th><th>Co je špatně</th><th class="cislo">Učitel</th><th class="cislo">Program</th></tr></thead><tbody>${radky}</tbody></table>` : ""));
  } catch (e) { chybaDialog(e); }
}
async function dlgPredikce() {
  try {
    const r = JSON.parse(await volej("predikce"));
    const radky = r.skupiny.map((g) => `<tr><td>${esc(g.co)}</td><td class="cislo">${g.program}</td><td class="cislo">${g.predpoved}</td><td>${esc(g.poznamka)}${g.vrstvy.length ? ' <span class="tlumene">(' + esc(g.vrstvy.join(", ")) + ")</span>" : ""}</td></tr>`).join("");
    dialog("Co nejspíš najde učitel", `<p class="stredni" style="color:${esc(r.barva)}">${esc(r.verdikt)}</p>` +
      `<p class="tlumene">Odhad: chybné atributy ${r.atributy} prvků (${r.skupin} skupin), topologie ${r.topologie}.</p>` +
      (r.pozor.length ? `<p>Pozor: ${esc(r.pozor.join("; "))}</p>` : "") +
      (radky ? `<table><thead><tr><th>Skupina</th><th class="cislo">Program</th><th class="cislo">Odhad</th><th>Poznámka</th></tr></thead><tbody>${radky}</tbody></table>` : ""));
  } catch (e) { chybaDialog(e); }
}

// ---------------------------------------------------------------- nastavení kontroly (Zadání)
const NAST_KLIC = "kv_nastaveni";
let seznamKontrol = [];
function nactiNastaveni() { try { return JSON.parse(localStorage.getItem(NAST_KLIC) || "{}") || {}; } catch (e) { return {}; } }
function ulozNastaveni() { try { localStorage.setItem(NAST_KLIC, JSON.stringify(nastaveniKontroly())); } catch (e) { /* bez úložiště */ } }
function nastaveniKontroly() {
  const n = { tolerance: parseFloat(String($("n_tolerance").value).replace(",", ".")) || 0.01, rozpracovany: $("n_rozpracovany").checked, vypnute: [], zapnute: [] };
  document.querySelectorAll("#n_kontroly [data-k]").forEach((i) => {
    const k = seznamKontrol.find((x) => x.id === i.dataset.k);
    if (k && i.checked !== k.zapnuto) (i.checked ? n.zapnute : n.vypnute).push(k.id);
  });
  return n;
}
async function nactiKontroly() {
  try { seznamKontrol = JSON.parse(await volej("kontroly")); } catch (e) { return; }
  const n = nactiNastaveni();
  if (n.tolerance) $("n_tolerance").value = n.tolerance;
  $("n_rozpracovany").checked = !!n.rozpracovany;
  const el = $("n_kontroly");
  el.innerHTML = "";
  let sk = null;
  for (const k of [...seznamKontrol].sort((a, b) => a.skupina.localeCompare(b.skupina, "cs"))) {
    if (k.skupina !== sk) { sk = k.skupina; const h = document.createElement("div"); h.className = "skupina-k"; h.textContent = sk; el.appendChild(h); }
    const zap = (n.vypnute || []).includes(k.id) ? false : (n.zapnute || []).includes(k.id) ? true : k.zapnuto;
    const l = document.createElement("label");
    l.className = "volba"; l.title = k.popis || "";
    l.innerHTML = `<input type="checkbox" data-k="${esc(k.id)}" ${zap ? "checked" : ""}> ${esc(k.nazev)}${k.pravidla ? ' <span class="tlumene">(podle pravidel)</span>' : ""}`;
    el.appendChild(l);
  }
}
$("n_kontroly").addEventListener("change", ulozNastaveni);
$("n_tolerance").addEventListener("change", ulozNastaveni);
$("n_rozpracovany").addEventListener("change", ulozNastaveni);
