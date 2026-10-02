// Webová verze – Výpočty: seznam souřadnic, polární metoda ze zápisníku a geodetické úlohy (stejné jako na desktopu).
"use strict";

const vyp = { body: [], ulohy: null, aktivni: null, hodnoty: {}, vysledek: null, zapisnik: null, cekajici: new Map(), dalsiId: 1, nove: new Set() };

// ---------------------------------------------------------------- volání Pythonu ve workeru
function volej(volani, args = [], soubor = null, soubory = null, sDaty = false) {
  return new Promise((ok, chyba) => {
    const id = vyp.dalsiId++;
    vyp.cekajici.set(id, { ok, chyba, sDaty });
    worker.postMessage({ volani, args, soubor, soubory, id });
  });
}
// volání, které vrací soubor ke stažení: {json, data}
function volejSoubor(volani, args = [], soubor = null, soubory = null) { return volej(volani, args, soubor, soubory, true); }
function vypOdpoved(m) {
  const c = vyp.cekajici.get(m.id);
  if (!c) return;
  vyp.cekajici.delete(m.id);
  skryjStavPrace();
  if (m.chybaVolani) c.chyba(new Error(m.chybaVolani));
  else c.ok(c.sDaty ? { json: JSON.parse(m.odpoved), data: m.data } : m.odpoved);
}
function skryjStavPrace() { if (vyp.praceStav) { vyp.praceStav = false; skryjStav(); } }
function stahniData(data, nazev) {
  nazev = nazev.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const typy = { pdf: "application/pdf", html: "text/html", xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", csv: "text/csv", dxf: "application/dxf" };
  const blob = new Blob([data], { type: typy[nazev.split(".").pop().toLowerCase()] || "application/octet-stream" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = nazev;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
async function vypPripraveno() {
  try {
    vyp.ulohy = JSON.parse(await volej("ulohy"));
  } catch (e) { vyp.ulohy = []; }
  vykresliUlohy();
  $("u_spocti").disabled = !vyp.aktivni;
  if (typeof nactiKontroly === "function") nactiKontroly();
}

// ---------------------------------------------------------------- seznam souřadnic (pamatuje si ho jen tento prohlížeč)
function ulozMistne() { try { localStorage.setItem("kv_body", JSON.stringify(vyp.body)); } catch (e) { /* soukromé okno */ } }
function nactiMistne() { try { const t = localStorage.getItem("kv_body"); if (t) vyp.body = JSON.parse(t) || []; } catch (e) { vyp.body = []; } }
const klic = (c) => String(c).split(/(\d+)/).filter(Boolean).map((p) => (/^\d+$/.test(p) ? p.padStart(12, "0") : p.toLowerCase())).join("");
function serad() { vyp.body.sort((a, b) => (klic(a.c) < klic(b.c) ? -1 : klic(a.c) > klic(b.c) ? 1 : 0)); }
const f2 = (v) => (v == null || v === "" ? "" : Number(v).toFixed(2));

function pridejBody(nove, oznacit = true) {
  let pridano = 0, nahrazeno = 0;
  const index = new Map(vyp.body.map((b, i) => [b.c, i]));
  for (const b of nove) {
    if (index.has(b.c)) { vyp.body[index.get(b.c)] = b; nahrazeno++; }
    else { index.set(b.c, vyp.body.length); vyp.body.push(b); pridano++; }
    if (oznacit) vyp.nove.add(b.c);
  }
  serad(); ulozMistne(); vykresliBody();
  return [pridano, nahrazeno];
}

function vykresliBody() {
  const t = ($("v_hledat").value || "").trim().toLowerCase();
  const tb = $("t_body").querySelector("tbody");
  tb.innerHTML = "";
  const vyber = vyp.body.filter((b) => !t || String(b.c).toLowerCase().includes(t) || (b.kod || "").toLowerCase().includes(t));
  for (const b of vyber.slice(0, 3000)) {
    const tr = document.createElement("tr");
    if (vyp.nove.has(b.c)) tr.className = "novy";
    [["c", b.c], ["y", f2(b.y)], ["x", f2(b.x)], ["z", f2(b.z)], ["kod", b.kod || ""]].forEach(([k, v]) => {
      const td = document.createElement("td"); td.textContent = v; td.title = "Dvojklik = upravit";
      td.addEventListener("dblclick", () => upravBunku(td, b, k));
      tr.appendChild(td);
    });
    const td = document.createElement("td");
    const x = document.createElement("button"); x.textContent = "✕"; x.title = "Smazat bod " + b.c; x.setAttribute("aria-label", "Smazat bod " + b.c);
    x.addEventListener("click", () => { vyp.body = vyp.body.filter((q) => q !== b); ulozMistne(); vykresliBody(); });
    td.appendChild(x); tr.appendChild(td);
    tb.appendChild(tr);
  }
  $("v_pocet").textContent = vyp.body.length ? `· ${vyp.body.length} bodů` : "";
  const dl = $("d_body"); dl.innerHTML = "";
  for (const b of vyp.body.slice(0, 5000)) { const o = document.createElement("option"); o.value = b.c; dl.appendChild(o); }
  kresliMapu();
}
$("v_hledat").addEventListener("input", vykresliBody);

function upravBunku(td, b, k) {
  const inp = document.createElement("input");
  inp.className = "bunka";
  inp.value = k === "c" || k === "kod" ? (b[k] || "") : (b[k] == null ? "" : b[k]);
  td.textContent = "";
  td.appendChild(inp);
  inp.focus(); inp.select();
  const hotovo = (ulozit) => {
    if (ulozit) {
      const t = inp.value.trim();
      if (k === "c" || k === "kod") { if (k === "kod" || t) b[k] = t; }
      else if (k === "z" && !t) b.z = null;
      else { const v = parseFloat(t.replace(",", ".")); if (isFinite(v)) b[k] = v; }
      serad(); ulozMistne();
    }
    vykresliBody();
  };
  inp.addEventListener("keydown", (e) => { if (e.key === "Enter") hotovo(true); if (e.key === "Escape") hotovo(false); });
  inp.addEventListener("blur", () => hotovo(true), { once: true });
}

function kresliMapu() {
  const c = $("v_mapa"), r = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  if (!w) return;
  c.width = w * r; c.height = h * r;
  const g = c.getContext("2d"); g.setTransform(r, 0, 0, r, 0, 0);
  g.fillStyle = "#05080C"; g.fillRect(0, 0, w, h);
  if (!vyp.body.length) return;
  // S-JTSK: Y doleva, X dolů → na obrazovce −Y vpravo, −X nahoru
  const ys = vyp.body.map((b) => -b.y), xs = vyp.body.map((b) => -b.x);
  const mx = Math.min(...ys), Mx = Math.max(...ys), my = Math.min(...xs), My = Math.max(...xs);
  const k = 0.88 * Math.min(w / Math.max(Mx - mx, 1e-6), h / Math.max(My - my, 1e-6));
  const sx = (v) => (v - (mx + Mx) / 2) * k + w / 2, sy = (v) => -(v - (my + My) / 2) * k + h / 2;
  g.font = "10px 'JetBrains Mono', monospace";
  for (const b of vyp.body.slice(0, 5000)) {
    const x = sx(-b.y), y = sy(-b.x);
    g.fillStyle = vyp.nove.has(b.c) ? "#2DD4BF" : "#C9D1D9";
    g.fillRect(x - 1.5, y - 1.5, 3, 3);
    if (vyp.body.length < 150) { g.fillStyle = "#8B98A5"; g.fillText(b.c, x + 4, y - 3); }
  }
}
window.addEventListener("resize", kresliMapu);

$("f_body").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  e.target.value = "";
  if (!f) return;
  if (!stav.pripraveno) { ukazStav("Počkejte, Python se ještě načítá…", false); setTimeout(skryjStav, 4000); return; }
  try {
    const d = JSON.parse(await volej("nacti_seznam", [], await nacti(f)));
    vyp.nove.clear();
    const [p, n] = pridejBody(d.body, false);
    ukazStav(`${f.name}: ${p} nových bodů` + (n ? `, ${n} přepsáno` : "") + (d.varovani.length ? ` · ${d.varovani.length} řádků přeskočeno (${d.varovani[0]})` : ""), false);
    setTimeout(skryjStav, 7000);
  } catch (err) { ukazStav("Seznam se nepodařilo načíst: " + err.message, false, true); setTimeout(skryjStav, 9000); }
});

$("f_novy").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = e.target, cis = (v) => parseFloat(String(v).replace(",", "."));
  const b = { c: f.c.value.trim(), y: cis(f.y.value), x: cis(f.x.value), z: f.z.value.trim() ? cis(f.z.value) : null, kod: "" };
  if (!b.c || !isFinite(b.y) || !isFinite(b.x) || (b.z != null && !isFinite(b.z))) { ukazStav("Zadejte číslo bodu a souřadnice Y, X (čísla).", false, true); setTimeout(skryjStav, 5000); return; }
  pridejBody([b]);
  f.reset(); f.c.focus();
});

$("b_ulozit_body").addEventListener("click", (e) => { e.stopPropagation(); $("m_ulozit").classList.toggle("skryte"); });
document.addEventListener("click", () => $("m_ulozit").classList.add("skryte"));
$("m_ulozit").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.akce === "duplicity") {
    try {
      const r = JSON.parse(await volej("duplicity", [JSON.stringify(vyp.body)]));
      vyp.nove = new Set(r.cisla); vykresliBody();
      dialog("Duplicity v seznamu souřadnic", `<pre>${esc(r.text)}</pre>` + (r.pocet ? '<p class="tlumene">Dotčené body jsou v tabulce zvýrazněné.</p>' : ""));
    } catch (e) { chybaDialog(e); }
    return;
  }
  if (b.dataset.akce === "porovnat") {
    const f = await vyberSoubor(".txt,.csv,.xyz,.sez,.pts,.ss");
    if (!f) return;
    try {
      const r = JSON.parse(await volej("porovnej_seznamy", [JSON.stringify(vyp.body), 3], f));
      vyp.vysledek = { protokol: r.protokol, nove: [] };
      $("u_protokol").textContent = r.protokol;
      $("u_stahnout").disabled = $("u_pdf").disabled = false;
      ukazStav(r.souhrn, false); setTimeout(skryjStav, 7000);
    } catch (e) { chybaDialog(e); }
    return;
  }
  if (b.dataset.smazat) {
    if (vyp.body.length && confirm(`Smazat všech ${vyp.body.length} bodů ze seznamu?`)) { vyp.body = []; vyp.nove.clear(); ulozMistne(); vykresliBody(); }
    return;
  }
  if (!vyp.body.length) return;
  const odd = b.dataset.odd;
  const text = await volej("seznam_text", [JSON.stringify(vyp.body), odd]);
  stahni(text, odd === ";" ? "seznam_souradnic.csv" : "seznam_souradnic.txt", odd === ";");
});

function ukazVysledek(r) {
  const ch = $("u_chyba");
  ch.classList.add("skryte");
  if (r.chyba) { ch.textContent = "⚠ " + r.chyba; ch.classList.remove("skryte"); $("u_pridat").disabled = true; return false; }
  vyp.vysledek = r;
  $("u_protokol").textContent = r.protokol;
  $("u_stahnout").disabled = $("u_pdf").disabled = false;
  const n = (r.nove || []).length;
  $("u_pridat").disabled = !n;
  $("u_pridat").textContent = n ? `Přidat ${n} ${n === 1 ? "bod" : n < 5 ? "body" : "bodů"} do seznamu` : "Přidat do seznamu";
  if (r.upozorneni && r.upozorneni.length) { ch.textContent = "Upozornění: " + r.upozorneni.slice(0, 3).join("; "); ch.classList.remove("skryte"); }
  return true;
}

function stahni(text, nazev, bom = false) {
  const blob = new Blob([(bom ? "﻿" : "") + text], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = nazev;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// ---------------------------------------------------------------- úlohy
const POLARNI = { nazev: "Zápisník a polární metoda", popis: "Zápisník měření (.zap z Gromy nebo GSI z Leica): úpravy stanovisek a záměr, polární metoda dávkou s protokolem jako v Gromě, vyrovnání sítě MNČ a kontrola výpočtu proti seznamu souřadnic.", pole: [], polarni: true };
const SKUPINY = [
  ["Ze zápisníku", ["Zápisník a polární metoda"]],
  ["Body", ["Směrník a délka", "Rajón (polární bod)", "Protínání vpřed z úhlů", "Protínání z délek", "Protínání zpět", "Volné stanovisko",
    "Průsečíky", "Staničení a kolmice", "Bod ze staničení a kolmice", "Ortogonální metoda", "Polygonový pořad", "Vytyčovací prvky", "Kružnicový oblouk"]],
  ["Plochy", ["Výměra a obvod", "Výměry parcel dávkou", "Oddělení parcely"]],
  ["Výšky a terén", ["Trigonometrická výška", "Nivelační pořad", "Vyrovnání nivelační sítě", "Model terénu a kubatura"]],
  ["Kontroly", ["Kontrola dvou určení", "Kontrolní oměrné míry"]],
  ["Transformace", ["Transformace", "Převod S-JTSK ↔ WGS84"]],
];

function vykresliUlohy() {
  const nav = $("v_ulohy");
  nav.innerHTML = "";
  const vsechny = [POLARNI, ...vyp.ulohy.map((u, i) => ({ ...u, index: i }))];
  const pouzite = new Set();
  const tlacitko = (u) => {
    const b = document.createElement("button");
    b.textContent = u.nazev;
    b.className = vyp.aktivni === u ? "aktivni" : "";
    b.addEventListener("click", () => vyberUlohu(u));
    u.tlacitko = b;
    nav.appendChild(b);
    pouzite.add(u.nazev);
  };
  for (const [sk, jmena] of SKUPINY) {
    const uu = jmena.map((j) => vsechny.find((u) => u.nazev === j)).filter(Boolean);
    if (!uu.length) continue;
    const h = document.createElement("div"); h.className = "skupina"; h.textContent = sk; nav.appendChild(h);
    uu.forEach(tlacitko);
  }
  const zbytek = vsechny.filter((u) => !pouzite.has(u.nazev));
  if (zbytek.length) { const h = document.createElement("div"); h.className = "skupina"; h.textContent = "Další"; nav.appendChild(h); zbytek.forEach(tlacitko); }
  if (!vyp.aktivni) vyberUlohu(vsechny[1] || POLARNI);
}

function vyberUlohu(u) {
  ulozHodnoty();
  vyp.aktivni = u;
  document.querySelectorAll("#v_ulohy button").forEach((b) => b.classList.toggle("aktivni", b === u.tlacitko));
  $("u_nazev").textContent = u.nazev;
  $("u_popis").textContent = u.popis;
  $("u_chyba").classList.add("skryte");
  const f = $("u_form");
  f.innerHTML = "";
  const ulozene = vyp.hodnoty[u.nazev] || {};
  if (u.polarni) vykresliZapisnik(f);
  for (const p of u.pole) {
    const l = document.createElement("label");
    if (p.typ === "radky") l.className = "siroke";
    const s = document.createElement("span"); s.textContent = p.label; l.appendChild(s);
    let el;
    if (p.typ === "volba") {
      el = document.createElement("select");
      for (const v of p.volby) { const o = document.createElement("option"); o.value = o.textContent = v; el.appendChild(o); }
    } else if (p.typ === "radky") {
      el = document.createElement("textarea"); el.rows = 4; el.spellcheck = false;
    } else {
      el = document.createElement("input");
      if (p.typ === "bod") { el.setAttribute("list", "d_body"); el.autocomplete = "off"; }
      if (p.typ === "gon" || p.typ === "m") el.inputMode = "decimal";
    }
    el.name = p.key;
    el.value = ulozene[p.key] != null ? ulozene[p.key] : (p.vychozi || (p.typ === "volba" ? p.volby[0] : ""));
    l.appendChild(el);
    if (p.napoveda) { const n = document.createElement("span"); n.className = "napoveda"; n.textContent = p.napoveda; l.appendChild(n); }
    f.appendChild(l);
  }
  $("u_spocti").disabled = !stav.pripraveno;
  $("u_dxf").classList.toggle("skryte", u.nazev !== "Model terénu a kubatura");
  for (const id of ["u_vyrovnat", "u_kontrola", "u_zap"]) $(id).classList.toggle("skryte", !u.polarni);
}

$("u_dxf").addEventListener("click", async () => {
  ulozHodnoty();
  const r = JSON.parse(await volej("vrstevnice_dxf", [JSON.stringify(vyp.body), JSON.stringify(vyp.hodnoty[vyp.aktivni.nazev])]));
  if (r.chyba) { $("u_chyba").textContent = "⚠ " + r.chyba; $("u_chyba").classList.remove("skryte"); return; }
  stahni(r.dxf, "vrstevnice.dxf");
  ukazStav(r.souhrn, false); setTimeout(skryjStav, 7000);
});

function ulozHodnoty() {
  const u = vyp.aktivni;
  if (!u) return;
  const h = {};
  for (const el of $("u_form").elements) if (el.name) h[el.name] = el.value;
  vyp.hodnoty[u.nazev] = h;
}

$("u_form").addEventListener("submit", (e) => { e.preventDefault(); spocti(); });
$("u_form").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); spocti(); } });
$("u_spocti").addEventListener("click", spocti);

async function spocti() {
  const u = vyp.aktivni;
  if (!u || !stav.pripraveno) return;
  ulozHodnoty();
  const ch = $("u_chyba");
  ch.classList.add("skryte");
  let r;
  try {
    if (u.polarni) {
      if (!zap.stanoviska.length) throw new Error("Načtěte zápisník měření (nebo přidejte stanovisko).");
      r = JSON.parse(await volej("polarni_zapisnik", [JSON.stringify(zap.stanoviska), JSON.stringify(vyp.body), zap.nazev]));
    } else {
      r = JSON.parse(await volej("spocti", [u.index, JSON.stringify(vyp.body), JSON.stringify(vyp.hodnoty[u.nazev])]));
    }
  } catch (e) { r = { chyba: e.message }; }
  ukazVysledek(r);
}

$("u_pridat").addEventListener("click", () => {
  const r = vyp.vysledek;
  if (!r || !r.nove || !r.nove.length) return;
  vyp.nove.clear();
  const [p, n] = pridejBody(r.nove);
  $("u_pridat").disabled = true;
  ukazStav(`Do seznamu přidáno ${p} bodů` + (n ? `, ${n} přepsáno (stejné číslo)` : "") + ".", false);
  setTimeout(skryjStav, 5000);
});
$("u_pdf").addEventListener("click", async () => {
  if (!vyp.vysledek) return;
  ukazStav("Připravuji PDF…");
  try {
    const { json, data } = await volejSoubor("protokol_pdf", [vyp.vysledek.protokol, "protokol_" + (vyp.aktivni.nazev || "vypocet").replace(/[^\p{L}\p{N}]+/gu, "_")]);
    skryjStav();
    stahniData(data, json.nazev);
  } catch (e) { skryjStav(); chybaDialog(e); }
});
$("u_stahnout").addEventListener("click", () => {
  if (vyp.vysledek) stahni(vyp.vysledek.protokol, "protokol_" + (vyp.aktivni.nazev || "vypocet").replace(/[^\p{L}\p{N}]+/gu, "_") + ".txt");
});

nactiMistne();
serad();
vykresliBody();
