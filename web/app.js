// Webová verze Kontroly výkresu: rozhraní, plátno s výkresem a seznam chyb. Výpočet běží ve worker.js (Pyodide).
"use strict";

const $ = (id) => document.getElementById(id);
const stav = { vykres: null, pravidla: null, seznam: null, pripraveno: false, vysledek: null, filtr: "vse", vybrana: null,
  skryteVrstvy: new Set(), obrys: null, znacky: [], vybranaZnacka: null };
const worker = new Worker("worker.js");

// ---------------------------------------------------------------- stavový řádek
function ukazStav(text, tocit = true, chyba = false) {
  const el = $("stav");
  el.classList.remove("skryte");
  el.classList.toggle("chyba-stav", chyba);
  el.querySelector(".tocitko").style.display = tocit ? "" : "none";
  $("stav_text").textContent = text;
}
function skryjStav() { $("stav").classList.add("skryte"); }

worker.onerror = (e) => {
  e.preventDefault();
  ukazStav("Python v prohlížeči se nepodařilo načíst (" + (e.message || "chyba sítě") + "). Zkontrolujte připojení k internetu a obnovte stránku.", false, true);
};
worker.onmessage = (ev) => {
  const m = ev.data;
  if (m.id) { vypOdpoved(m); return; }
  if (m.stav) { ukazStav(m.stav); if (m.prace && stav.pripraveno) vyp.praceStav = true; }
  if (m.pripraveno) {
    stav.pripraveno = true;
    skryjStav();
    aktualizujTlacitko();
    vypPripraveno();
    if (stav.vykres && stav.cekat) { stav.cekat = false; zkontroluj(); }
  }
  if (m.chyba) { ukazStav(m.chyba, false, true); setTimeout(skryjStav, 12000); }
  if (m.vysledek) { skryjStav(); zobrazVysledek(JSON.parse(m.vysledek)); }
};

// ---------------------------------------------------------------- stránky
document.querySelectorAll(".stranka").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".stranka").forEach((x) => x.classList.toggle("aktivni", x === b));
  for (const s of ["vykres", "vypocty", "podklady", "o"]) $("s_" + s).classList.toggle("skryte", s !== b.dataset.stranka);
  if (b.dataset.stranka === "vykres") prekresli();
  if (b.dataset.stranka === "vypocty") kresliMapu();
}));

// ---------------------------------------------------------------- soubory
async function nacti(file) { return { nazev: file.name, data: await file.arrayBuffer() }; }
async function otevriVykres(file) {
  if (!file) return;
  if (!/\.(dxf|dgn)$/i.test(file.name)) { ukazStav("Výkres musí být DXF nebo DGN.", false, true); setTimeout(skryjStav, 5000); return; }
  stav.vykres = await nacti(file);
  $("soubor").textContent = file.name;
  $("podtitul").textContent = "Kontrola v prohlížeči · výkres se nikam neodesílá";
  aktualizujTlacitko();
  if (stav.pripraveno) zkontroluj(); else { stav.cekat = true; ukazStav("Připravuji kontrolu – výkres se zkontroluje sám…"); }
}
$("f_vykres").addEventListener("change", (e) => otevriVykres(e.target.files[0]));
$("f_vykres2").addEventListener("change", (e) => otevriVykres(e.target.files[0]));
$("f_pravidla").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  stav.pravidla = await nacti(f);
  document.querySelector("input[name=pravidla][value=soubor]").checked = true;
  $("i_pravidla").textContent = "Načteno: " + f.name;
});
$("f_seznam").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  stav.seznam = await nacti(f);
  $("i_seznam").textContent = "Načteno: " + f.name;
});

const obal = document.querySelector(".platno-obal");
["dragenter", "dragover"].forEach((t) => obal.addEventListener(t, (e) => { e.preventDefault(); $("pretazeni").classList.add("nad"); }));
["dragleave", "drop"].forEach((t) => obal.addEventListener(t, (e) => { e.preventDefault(); $("pretazeni").classList.remove("nad"); }));
obal.addEventListener("drop", (e) => {
  for (const f of e.dataTransfer.files) {
    if (/\.(dxf|dgn)$/i.test(f.name)) otevriVykres(f);
    else if (/\.(yaml|yml|xls|xlsx|csv|ods|doc|docx)$/i.test(f.name)) { $("f_pravidla").files = e.dataTransfer.files; $("f_pravidla").dispatchEvent(new Event("change")); }
    else if (/\.(txt|xyz|sez|pts)$/i.test(f.name)) nacti(f).then((d) => { stav.seznam = d; $("i_seznam").textContent = "Načteno: " + f.name; });
  }
});

function aktualizujTlacitko() { $("b_kontrola").disabled = !(stav.vykres && stav.pripraveno); }
$("b_kontrola").addEventListener("click", zkontroluj);

function zkontroluj() {
  if (!stav.vykres || !stav.pripraveno) return;
  const volba = document.querySelector("input[name=pravidla]:checked").value;
  worker.postMessage({
    vykres: stav.vykres,
    pravidla: volba === "soubor" ? stav.pravidla : null,
    vestavena: volba === "zadani1" ? "pravidla/zadani1.yaml" : null,
    seznam: stav.seznam,
    meritko: parseInt($("meritko").value, 10) || null,
    nastaveni: typeof nastaveniKontroly === "function" ? JSON.stringify(nastaveniKontroly()) : null,
  });
}

// ---------------------------------------------------------------- výsledek
const POPIS = { "chyba": "chyby", "varování": "varování", "info": "info" };
function zobrazVysledek(v) {
  stav.vysledek = v;
  stav.vybrana = null;
  $("pretazeni").classList.add("skryte");
  $("podtitul").textContent = `${v.prvku} prvků · ${v.vrstev} hladin · ${v.pravidel} pravidel`;
  const s = v.skore.hodnota;
  $("skore").textContent = s;
  $("prstenec").style.background = `conic-gradient(${barvaSkore(s)} 0 ${s}%, var(--linka) ${s}% 100%)`;
  $("skore_popis").textContent = v.skore.popis;
  const pocty = { "chyba": 0, "varování": 0, "info": 0 };
  v.chyby.forEach((c) => { pocty[c.zavaznost] = (pocty[c.zavaznost] || 0) + 1; });
  $("skore_souhrn").textContent = v.chyby.length ? `${v.chyby.length} nálezů k prohlédnutí.` : "Bez nálezů – výkres je v pořádku.";
  $("stitky").innerHTML = "";
  for (const [k, n] of Object.entries(pocty)) {
    if (!n) continue;
    const el = document.createElement("span");
    el.className = "stitek " + k;
    el.textContent = `${n} ${POPIS[k] || k}`;
    $("stitky").appendChild(el);
  }
  if (v.varovani && v.varovani.length) {
    ukazStav(v.varovani[0], false);
    setTimeout(skryjStav, 8000);
  }
  stav.skryteVrstvy.clear(); stav.obrys = null; stav.znacky = [];
  $("b_nastroje").disabled = false;
  if (typeof vykresliHladiny === "function") vykresliHladiny();
  vykresliSeznam();
  pohled.vse();
}
function barvaSkore(s) { return s >= 80 ? "var(--akcent)" : s >= 50 ? "var(--varovani)" : "var(--chyba)"; }

document.querySelectorAll(".filtr").forEach((b) => b.addEventListener("click", () => {
  stav.filtr = b.dataset.f;
  document.querySelectorAll(".filtr").forEach((x) => x.classList.toggle("aktivni", x === b));
  vykresliSeznam();
}));

function vykresliSeznam() {
  const sez = $("seznam");
  sez.innerHTML = "";
  const v = stav.vysledek;
  if (!v) return;
  const chyby = v.chyby.filter((c) => stav.filtr === "vse" || c.zavaznost === stav.filtr);
  if (!chyby.length) { sez.innerHTML = '<div class="prazdne">Nic k zobrazení.</div>'; return; }
  for (const c of chyby.slice(0, 1500)) {
    const b = document.createElement("button");
    b.className = "chyba-karta" + (stav.vybrana === c.id ? " vybrana" : "");
    const hlava = document.createElement("div");
    hlava.className = "chyba-hlava";
    hlava.innerHTML = `<span class="tecka ${c.zavaznost}"></span>`;
    const n = document.createElement("span"); n.className = "chyba-nazev"; n.textContent = c.kontrola; hlava.appendChild(n);
    const l = document.createElement("span"); l.className = "chyba-vrstva"; l.textContent = c.vrstva; hlava.appendChild(l);
    const z = document.createElement("div"); z.className = "chyba-zprava"; z.textContent = c.zprava;
    b.append(hlava, z);
    if (stav.vybrana === c.id && c.navod) {
      const nv = document.createElement("div"); nv.className = "navod"; nv.textContent = c.navod; b.appendChild(nv);
    }
    b.addEventListener("click", () => { stav.vybrana = c.id; vykresliSeznam(); if (c.x != null) pohled.na(c.x, c.y); else prekresli(); });
    sez.appendChild(b);
  }
}

// ---------------------------------------------------------------- plátno
const platno = $("platno");
const ctx = platno.getContext("2d");
const pohled = {
  cx: 0, cy: 0, k: 1,
  vse() {
    const b = stav.vysledek && stav.vysledek.kresba.bounds;
    velikost();
    if (!b) { prekresli(); return; }
    const w = platno.clientWidth, h = platno.clientHeight;
    this.cx = (b[0] + b[2]) / 2; this.cy = (b[1] + b[3]) / 2;
    this.k = 0.92 * Math.min(w / Math.max(b[2] - b[0], 1e-6), h / Math.max(b[3] - b[1], 1e-6));
    prekresli();
  },
  na(x, y) {
    this.cx = x; this.cy = y;
    const w = platno.clientWidth;
    this.k = Math.max(this.k, w / 60); // přiblížit na okolí ~60 m
    prekresli();
  },
  sx(x) { return (x - this.cx) * this.k + platno.clientWidth / 2; },
  sy(y) { return -(y - this.cy) * this.k + platno.clientHeight / 2; },
  wx(px) { return (px - platno.clientWidth / 2) / this.k + this.cx; },
  wy(py) { return -(py - platno.clientHeight / 2) / this.k + this.cy; },
};
$("z_vse").addEventListener("click", () => pohled.vse());

function velikost() {
  const r = window.devicePixelRatio || 1;
  const w = platno.clientWidth, h = platno.clientHeight;
  if (platno.width !== Math.round(w * r) || platno.height !== Math.round(h * r)) {
    platno.width = Math.round(w * r); platno.height = Math.round(h * r);
  }
  ctx.setTransform(r, 0, 0, r, 0, 0);
}
let naplanovano = false;
function prekresli() {
  if (naplanovano) return;
  naplanovano = true;
  requestAnimationFrame(() => { naplanovano = false; kresli(); });
}
window.addEventListener("resize", prekresli);

const BARVY_Z = { "chyba": "#F87171", "varování": "#F59E0B", "info": "#60A5FA" };
function kresli() {
  velikost();
  const w = platno.clientWidth, h = platno.clientHeight;
  ctx.fillStyle = "#05080C";
  ctx.fillRect(0, 0, w, h);
  const v = stav.vysledek;
  if (!v) return;
  const k = v.kresba;
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  const skryte = stav.skryteVrstvy;
  for (const c of k.cary) {
    if (skryte.size && skryte.has(c.l)) continue;
    const p = c.p;
    ctx.strokeStyle = c.c;
    ctx.lineWidth = c.w > 0.25 ? Math.min(4, 1 + c.w * 3) : 1;
    ctx.beginPath();
    ctx.moveTo(pohled.sx(p[0]), pohled.sy(p[1]));
    for (let i = 2; i < p.length; i += 2) ctx.lineTo(pohled.sx(p[i]), pohled.sy(p[i + 1]));
    ctx.stroke();
  }
  for (const b of k.body) {
    if (skryte.size && skryte.has(b[4])) continue;
    const x = pohled.sx(b[0]), y = pohled.sy(b[1]);
    if (x < -10 || y < -10 || x > w + 10 || y > h + 10) continue;
    ctx.fillStyle = b[2];
    if (b[3]) { ctx.strokeStyle = b[2]; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(x, y, 4, 0, 7); ctx.stroke(); }
    else ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
  }
  for (const t of k.texty) {
    if (skryte.size && skryte.has(t.l)) continue;
    const vys = t.h * pohled.k;
    if (vys < 5) continue;
    const x = pohled.sx(t.x), y = pohled.sy(t.y);
    if (x < -400 || y < -200 || x > w + 400 || y > h + 200) continue;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(-t.r * Math.PI / 180);
    ctx.fillStyle = t.c;
    ctx.font = `${Math.min(vys, 200)}px 'IBM Plex Sans', sans-serif`;
    ctx.fillText(t.t, 0, 0);
    ctx.restore();
  }
  if (stav.obrys) {  // vybraný prvek (inspektor)
    ctx.strokeStyle = "#FDE047"; ctx.lineWidth = 3;
    for (const p of stav.obrys) {
      ctx.beginPath(); ctx.moveTo(pohled.sx(p[0]), pohled.sy(p[1]));
      for (let i = 2; i < p.length; i += 2) ctx.lineTo(pohled.sx(p[i]), pohled.sy(p[i + 1]));
      ctx.stroke();
    }
  }
  for (const z of stav.znacky) {  // změny proti starší verzi
    const x = pohled.sx(z.x), y = pohled.sy(z.y);
    if (x < -20 || y < -20 || x > w + 20 || y > h + 20) continue;
    ctx.strokeStyle = z.druh.startsWith("přid") ? "#34D399" : z.druh.startsWith("odeb") ? "#F87171" : "#FBBF24";
    ctx.lineWidth = z === stav.vybranaZnacka ? 3.5 : 2;
    const r = z === stav.vybranaZnacka ? 14 : 8;
    ctx.strokeRect(x - r, y - r, 2 * r, 2 * r);
  }
  for (const c of v.chyby) {
    if (stav.panel === "zmeny") break;
    if (c.x == null || (stav.filtr !== "vse" && c.zavaznost !== stav.filtr)) continue;
    const x = pohled.sx(c.x), y = pohled.sy(c.y);
    if (x < -20 || y < -20 || x > w + 20 || y > h + 20) continue;
    const vyb = stav.vybrana === c.id;
    ctx.strokeStyle = BARVY_Z[c.zavaznost] || "#F87171";
    ctx.lineWidth = vyb ? 3.5 : 2;
    ctx.beginPath(); ctx.arc(x, y, vyb ? 18 : 11, 0, 7); ctx.stroke();
  }
}

// posun (tažení), zoom (kolečko, dvěma prsty), klik na chybu
const prsty = new Map();
let tah = null, rozpeti = null;
platno.addEventListener("pointerdown", (e) => {
  platno.setPointerCapture(e.pointerId);
  prsty.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
  tah = { x: e.offsetX, y: e.offsetY, cx: pohled.cx, cy: pohled.cy, posun: 0 };
  if (prsty.size === 2) {
    const [a, b] = [...prsty.values()];
    rozpeti = { d: Math.hypot(a.x - b.x, a.y - b.y), k: pohled.k };
  }
});
platno.addEventListener("pointermove", (e) => {
  $("souradnice").textContent = `Y ${(-pohled.wx(e.offsetX)).toFixed(2)}   X ${(-pohled.wy(e.offsetY)).toFixed(2)}`;
  if (!prsty.has(e.pointerId)) return;
  prsty.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
  if (prsty.size === 2 && rozpeti) {
    const [a, b] = [...prsty.values()];
    pohled.k = rozpeti.k * Math.hypot(a.x - b.x, a.y - b.y) / Math.max(rozpeti.d, 1);
    prekresli();
    return;
  }
  if (tah) {
    const dx = e.offsetX - tah.x, dy = e.offsetY - tah.y;
    tah.posun = Math.max(tah.posun, Math.abs(dx) + Math.abs(dy));
    pohled.cx = tah.cx - dx / pohled.k; pohled.cy = tah.cy + dy / pohled.k;
    prekresli();
  }
});
platno.addEventListener("pointerup", (e) => {
  prsty.delete(e.pointerId);
  if (prsty.size < 2) rozpeti = null;
  if (tah && tah.posun < 5 && stav.vysledek) vyberChybuNa(e.offsetX, e.offsetY);
  tah = null;
});
platno.addEventListener("wheel", (e) => {
  e.preventDefault();
  const x = pohled.wx(e.offsetX), y = pohled.wy(e.offsetY);
  pohled.k *= Math.pow(1.0015, -e.deltaY);
  pohled.cx = x - (e.offsetX - platno.clientWidth / 2) / pohled.k;
  pohled.cy = y + (e.offsetY - platno.clientHeight / 2) / pohled.k;
  prekresli();
}, { passive: false });

function vyberChybuNa(px, py) {
  let nej = null, d = 22;
  if (stav.panel === "zmeny" && typeof vyberZmenuNa === "function") { vyberZmenuNa(px, py); return; }
  for (const c of stav.panel === "prvek" ? [] : stav.vysledek.chyby) {
    if (c.x == null) continue;
    const dd = Math.hypot(pohled.sx(c.x) - px, pohled.sy(c.y) - py);
    if (dd < d) { d = dd; nej = c; }
  }
  if (!nej || stav.panel === "prvek") { if (typeof inspektor === "function") inspektor(px, py); return; }
  if (nej) {
    stav.vybrana = nej.id;
    stav.filtr = "vse";
    document.querySelectorAll(".filtr").forEach((x) => x.classList.toggle("aktivni", x.dataset.f === "vse"));
    vykresliSeznam();
    prekresli();
    const el = document.querySelector(".chyba-karta.vybrana");
    if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

ukazStav("Spouštím Python v prohlížeči…");
prekresli();
