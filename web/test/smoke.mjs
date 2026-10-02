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
await b.close();
if (skore === "–" || karet < 1 || chyby.length) {
  console.error("Webová verze nefunguje:", stavText, chyby);
  process.exit(1);
}
