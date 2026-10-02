// Webová verze – zápisník měření (jako zápisník Gromy): stanoviska a záměry k úpravě, uložení .zap / GSI,
// vyrovnání sítě MNČ a kontrola výpočtu proti seznamu souřadnic. Polární metodu spouští tlačítko Vypočítat.
"use strict";

const zap = { stanoviska: [], nazev: "", aktivni: 0 };
const ZAP_KLIC = "kv_zapisnik";
function ulozZap() { try { localStorage.setItem(ZAP_KLIC, JSON.stringify({ stanoviska: zap.stanoviska, nazev: zap.nazev })); } catch (e) { /* bez úložiště */ } }
try { const z = JSON.parse(localStorage.getItem(ZAP_KLIC) || "null"); if (z && Array.isArray(z.stanoviska)) { zap.stanoviska = z.stanoviska; zap.nazev = z.nazev || ""; } } catch (e) { /* nic */ }

const SLOUPCE_ZAP = [["bod", "Bod", 0], ["sd", "Šikmá délka", 3], ["vc", "Výška cíle", 3], ["hz", "Hz [g]", 4], ["z", "Z [g]", 4]];

function vykresliZapisnik(f) {
  const obal = document.createElement("div");
  obal.className = "siroke zapisnik";
  obal.innerHTML = `
    <div class="zap-lista">
      <label class="tlacitko maly">Načíst zápisník…<input type="file" accept=".zap,.gsi,.gs1,.gs2,.txt" hidden></label>
      <button type="button" class="tlacitko maly" data-a="nove_st">+ Stanovisko</button>
      <button type="button" class="tlacitko maly" data-a="smaz_st">Smazat stanovisko</button>
      <span class="tlumene zap-info"></span>
    </div>
    <div class="zap-st"></div>
    <div class="zap-hlava"></div>
    <div class="tabulka-obal zap-tab"><table class="tabulka"><thead><tr><th>Druh</th>${SLOUPCE_ZAP.map((s) => `<th>${s[1]}</th>`).join("")}<th></th></tr></thead><tbody></tbody></table></div>
    <div class="zap-lista"><button type="button" class="tlacitko maly" data-a="nova_o">+ Orientace</button><button type="button" class="tlacitko maly" data-a="nova_d">+ Podrobný bod</button>
      <span class="napoveda">Dané body (stanoviska a orientace) musí být v seznamu souřadnic. Úpravy se hned ukládají.</span></div>`;
  f.appendChild(obal);
  obal.querySelector("input[type=file]").addEventListener("change", async (e) => {
    const s = e.target.files[0];
    e.target.value = "";
    if (!s) return;
    try {
      const r = JSON.parse(await volej("nacti_zapisnik", [JSON.stringify(vyp.body)], await nacti(s)));
      zap.stanoviska = r.stanoviska; zap.nazev = s.name.replace(/\.[^.]+$/, ""); zap.aktivni = 0;
      ulozZap(); prekresliZap(obal);
      if (r.upozorneni.length) { $("u_chyba").textContent = "Upozornění v zápisníku: " + r.upozorneni.slice(0, 4).join("; "); $("u_chyba").classList.remove("skryte"); }
    } catch (err) { chybaDialog(err); }
  });
  obal.addEventListener("click", (e) => {
    const a = e.target.closest("[data-a]");
    if (!a) return;
    const st = zap.stanoviska[zap.aktivni];
    if (a.dataset.a === "nove_st") {
      const c = prompt("Číslo stanoviska:");
      if (!c) return;
      zap.stanoviska.push({ bod: c.trim(), vp: 0, orient: [], detail: [] }); zap.aktivni = zap.stanoviska.length - 1;
    } else if (a.dataset.a === "smaz_st") {
      if (!st || !confirm(`Smazat stanovisko ${st.bod} se všemi záměrami?`)) return;
      zap.stanoviska.splice(zap.aktivni, 1); zap.aktivni = Math.max(0, zap.aktivni - 1);
    } else if (st && (a.dataset.a === "nova_o" || a.dataset.a === "nova_d")) {
      (a.dataset.a === "nova_o" ? st.orient : st.detail).push({ bod: "", sd: 0, vc: 0, hz: 0, z: 100 });
    } else return;
    ulozZap(); prekresliZap(obal);
  });
  prekresliZap(obal);
}

function prekresliZap(obal) {
  const n = zap.stanoviska.reduce((s, st) => s + st.orient.length + st.detail.length, 0);
  obal.querySelector(".zap-info").textContent = zap.stanoviska.length ? `${zap.nazev || "zápisník"}: ${zap.stanoviska.length} stanovisek, ${n} záměr` : "Zápisník je prázdný.";
  const sez = obal.querySelector(".zap-st");
  sez.innerHTML = "";
  zap.stanoviska.forEach((st, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "filtr" + (i === zap.aktivni ? " aktivni" : "");
    b.textContent = `${st.bod} (${st.orient.length + st.detail.length})`;
    b.addEventListener("click", () => { zap.aktivni = i; prekresliZap(obal); });
    sez.appendChild(b);
  });
  const st = zap.stanoviska[zap.aktivni];
  const hl = obal.querySelector(".zap-hlava");
  hl.innerHTML = "";
  const tb = obal.querySelector("tbody");
  tb.innerHTML = "";
  if (!st) return;
  hl.innerHTML = `<label>Stanovisko <input class="pole" data-st="bod" value="${esc(st.bod)}"></label><label>Výška přístroje [m] <input class="pole" data-st="vp" inputmode="decimal" value="${st.vp}"></label>`;
  hl.querySelectorAll("input").forEach((i) => i.addEventListener("change", () => {
    st[i.dataset.st] = i.dataset.st === "vp" ? cislo(i.value, st.vp) : i.value.trim();
    ulozZap(); prekresliZap(obal);
  }));
  for (const [druh, seznam] of [["orientace", st.orient], ["podrobný", st.detail]]) {
    seznam.forEach((o, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="druh-${druh === "orientace" ? "o" : "d"}">${druh}</td>` +
        SLOUPCE_ZAP.map(([k, , d]) => `<td><input class="bunka" data-k="${k}" value="${esc(d ? Number(o[k]).toFixed(d) : o[k])}" ${d ? 'inputmode="decimal"' : ""} aria-label="${k}"></td>`).join("") +
        '<td><button type="button" title="Smazat záměru" aria-label="Smazat záměru">✕</button></td>';
      tr.querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
        o[inp.dataset.k] = inp.dataset.k === "bod" ? inp.value.trim() : cislo(inp.value, o[inp.dataset.k]);
        ulozZap();
      }));
      tr.querySelector("button").addEventListener("click", () => { seznam.splice(i, 1); ulozZap(); prekresliZap(obal); });
      tb.appendChild(tr);
    });
  }
}
function cislo(t, vych) { const v = parseFloat(String(t).replace(",", ".")); return isFinite(v) ? v : vych; }

// ---------------------------------------------------------------- vyrovnání sítě a kontrola výpočtu
$("u_vyrovnat").addEventListener("click", () => {
  if (!zap.stanoviska.length) return chybaDialog(new Error("Načtěte zápisník měření."));
  dialog("Vyrovnání sítě (MNČ)", `<p class="tlumene">Směry a vodorovné délky ze zápisníku, pevné body ze seznamu souřadnic. Body určené jen jednou (rajóny) spočítá polární metoda.</p>
    <div class="u-form"><label>Střední chyba směru [cc]<input class="pole" id="v_s1" value="10" inputmode="decimal"></label>
    <label>Střední chyba délky [mm]<input class="pole" id="v_s2" value="3" inputmode="decimal"></label>
    <label>Délka – část úměrná [ppm]<input class="pole" id="v_s3" value="2" inputmode="decimal"></label></div>`,
  [["Vyrovnat", async () => {
    const a = [cislo($("v_s1").value, 10), cislo($("v_s2").value, 3), cislo($("v_s3").value, 2)];
    $("dlg").close();
    try {
      const r = JSON.parse(await volej("vyrovnani", [JSON.stringify(zap.stanoviska), JSON.stringify(vyp.body), ...a]));
      if (ukazVysledek(r)) { ukazStav(r.souhrn, false); setTimeout(skryjStav, 7000); }
    } catch (e) { chybaDialog(e); }
  }, true]]);
});

$("u_kontrola").addEventListener("click", () => {
  if (!zap.stanoviska.length) return chybaDialog(new Error("Načtěte zápisník měření."));
  dialog("Kontrola výpočtu souřadnic", `<p class="tlumene">Aplikace sama spočítá polární metodu ze zápisníku (dané body ze seznamu souřadnic) a porovná ji se seznamem souřadnic, který jste vypočítali v Gromě. U rozdílů napíše pravděpodobnou příčinu.</p>
    <div class="u-form"><label>Tolerance polohy [m]<input class="pole" id="k_xy" value="0.01" inputmode="decimal"></label>
    <label>Tolerance výšky [m]<input class="pole" id="k_z" value="0.01" inputmode="decimal"></label></div>`,
  [["Vybrat seznam z Gromy a zkontrolovat", async () => {
    const tol = [cislo($("k_xy").value, 0.01), cislo($("k_z").value, 0.01)];
    const f = await vyberSoubor(".txt,.csv,.xyz,.sez,.pts,.ss");
    if (!f) return;
    $("dlg").close();
    try {
      const r = JSON.parse(await volej("kontrola_vypoctu", [JSON.stringify(zap.stanoviska), JSON.stringify(vyp.body), ...tol], f));
      if (ukazVysledek(r)) { ukazStav(r.rozdilu ? `Rozdílů nad toleranci: ${r.rozdilu} z ${r.bodu} bodů.` : `Všech ${r.bodu} bodů sedí.`, false); setTimeout(skryjStav, 8000); }
    } catch (e) { chybaDialog(e); }
  }, true]]);
});

$("u_zap").addEventListener("click", () => {
  if (!zap.stanoviska.length) return chybaDialog(new Error("Zápisník je prázdný."));
  dialog("Uložit zápisník", "<p>Formát souboru:</p>", [
    ["Groma (.zap)", () => ulozZapSoubor("zap"), true], ["Leica GSI-16 (.gsi)", () => ulozZapSoubor("gsi")]]);
});
async function ulozZapSoubor(druh) {
  $("dlg").close();
  try {
    const { json, data } = await volejSoubor("zapisnik_soubor", [JSON.stringify(zap.stanoviska), druh, zap.nazev || "zapisnik"]);
    stahniData(data, json.nazev);
  } catch (e) { chybaDialog(e); }
}
