// Ověření webové verze ve skutečném prohlížeči: nahraje výkres, počká na kontrolu, zkontroluje výsledek.
import { chromium } from "playwright";
const URL = process.env.WEB_URL || "http://localhost:8765/index.html";
const VYKRES = process.env.VYKRES || "podklady/zadani1-microstation/Vcelak_13_navic.dxf";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
const chyby = [];
p.on("pageerror", (e) => chyby.push(e.message));
p.on("console", (m) => console.log("konzole:", m.text().slice(0, 200)));
await p.goto(URL);
await p.setInputFiles("#f_vykres2", VYKRES);
const t0 = Date.now();
await p.waitForFunction(() => document.getElementById("skore").textContent !== "–" ||
  document.getElementById("stav").classList.contains("chyba-stav"), null, { timeout: 300000 });
const skore = await p.textContent("#skore");
const stavText = await p.textContent("#stav_text");
const karet = await p.locator(".chyba-karta").count();
console.log(`Hotovo za ${(Date.now() - t0) / 1000} s, skóre ${skore}, karet ${karet}, stav: ${stavText}`);
await p.screenshot({ path: "web-snimek.png" });
await p.locator(".chyba-karta").first().click();
await p.setViewportSize({ width: 390, height: 844 });
await p.screenshot({ path: "web-snimek-mobil.png" });
// Výpočty: seznam souřadnic, úloha a polární metoda ze zápisníku
const H = "podklady/zadani2-husovice/";
await p.setViewportSize({ width: 1440, height: 900 });
await p.click("button[data-stranka=vypocty]");
await p.setInputFiles("#f_body", H + "dane_body.txt");
await p.waitForFunction(() => document.querySelectorAll("#t_body tbody tr").length > 0, null, { timeout: 60000 });
await p.fill("#u_form [name=a]", "4001");
await p.fill("#u_form [name=b]", "4002");
await p.click("#u_spocti");
await p.waitForFunction(() => document.getElementById("u_protokol").textContent.includes("směrník"), null, { timeout: 60000 });
await p.click("#v_ulohy button:has-text('Polární metoda')");
await p.setInputFiles("#u_form input[type=file]", H + "zap_husovice.zap");
await p.waitForTimeout(500);
await p.click("#u_spocti");
await p.waitForFunction(() => !document.getElementById("u_pridat").disabled, null, { timeout: 120000 });
await p.click("#u_pridat");
const bodu = await p.locator("#t_body tbody tr").count();
console.log("Výpočty: bodů v seznamu po polární metodě", bodu);
await p.click("#v_ulohy button:has-text('Model terénu')");
await p.fill("#u_form [name=interval]", "0.5");
await p.click("#u_spocti");
await p.waitForFunction(() => document.getElementById("u_protokol").textContent.includes("trojúhelníků TIN"), null, { timeout: 60000 });
const [dl] = await Promise.all([p.waitForEvent("download"), p.click("#u_dxf")]);
console.log("DXF:", dl.suggestedFilename());
await p.screenshot({ path: "web-snimek-vypocty.png" });
await b.close();
if (bodu < 50) { console.error("Výpočty ve webové verzi nefungují."); process.exit(1); }
if (skore === "–" || karet < 1 || chyby.length) {
  console.error("Webová verze nefunguje:", stavText, chyby);
  process.exit(1);
}
