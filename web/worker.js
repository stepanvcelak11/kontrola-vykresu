// Výpočetní vlákno webové verze: Python (Pyodide) s jádrem Kontroly výkresu. Soubory zůstávají v prohlížeči.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.2/full/";
importScripts(PYODIDE + "pyodide.js");

let py = null;

async function start() {
  postMessage({ stav: "Spouštím Python v prohlížeči…", krok: 1 });
  py = await loadPyodide({ indexURL: PYODIDE });
  postMessage({ stav: "Načítám knihovny (numpy, shapely)…", krok: 2 });
  await py.loadPackage(["numpy", "shapely", "pyyaml", "micropip"]);
  postMessage({ stav: "Načítám knihovny (ezdxf, Excel, DGN)…", krok: 3 });
  const micropip = py.pyimport("micropip");
  await micropip.install(["ezdxf", "olefile", "openpyxl", "xlrd"]);
  postMessage({ stav: "Načítám aplikaci…", krok: 4 });
  const odp = await fetch("kontrola.zip", { cache: "no-cache" });
  if (!odp.ok) throw new Error("Soubor aplikace kontrola.zip se nepodařilo stáhnout (" + odp.status + ").");
  py.unpackArchive(await odp.arrayBuffer(), "zip", { extractDir: "/app" });
  py.runPython("import sys; sys.path.insert(0, '/app'); import kontrola.web_api");
  postMessage({ pripraveno: true });
}

const hotovo = start().catch((e) => postMessage({ chyba: "Spuštění se nepovedlo: " + e }));

function zapis(soubor) {
  if (!soubor) return null;
  const cesta = "/data/" + soubor.nazev.replace(/[\\/]/g, "_");
  py.FS.mkdirTree("/data");
  py.FS.writeFile(cesta, new Uint8Array(soubor.data));
  return cesta;
}

// PDF (reportlab) a písma s diakritikou se načtou až při prvním exportu do PDF
const PDF_VOLANI = new Set(["export", "protokol_pdf"]);
let pdfPripraveno = null;
function pripravPdf() {
  if (!pdfPripraveno) pdfPripraveno = (async () => {
    postMessage({ stav: "Načítám knihovnu pro PDF (jen poprvé)…", prace: true });
    await py.pyimport("micropip").install(["reportlab"]);
    const cil = "/usr/share/fonts/truetype/dejavu/";
    py.FS.mkdirTree(cil);
    for (const f of ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansMono.ttf"]) {
      try {
        const r = await fetch("fonty/" + f);
        if (r.ok) py.FS.writeFile(cil + f, new Uint8Array(await r.arrayBuffer()));
      } catch (e) { /* bez písma: PDF bez diakritiky */ }
    }
  })();
  return pdfPripraveno;
}

// Volání funkcí aplikace: {id, volani, args, soubor, soubory} → {id, odpoved[, data]} nebo {id, chybaVolani}
async function volej(m) {
  try {
    if (PDF_VOLANI.has(m.volani) && !(m.volani === "export" && !["pdf", "oprava"].includes((m.args || [])[0]))) await pripravPdf();
    const api = py.pyimport("kontrola.web_api");
    const args = [...(m.args || [])];
    if (m.soubory) for (const f of [...m.soubory].reverse()) args.unshift(zapis(f));
    if (m.soubor) args.unshift(zapis(m.soubor));
    const odpoved = api[m.volani](...args);
    let data = null;
    if (typeof odpoved === "string" && odpoved.startsWith("{") && odpoved.includes('"soubor"')) {
      try {
        const o = JSON.parse(odpoved);
        if (o.soubor && o.soubor.startsWith("/")) data = py.FS.readFile(o.soubor).buffer;
      } catch (e) { /* není soubor */ }
    }
    if (data) postMessage({ id: m.id, odpoved, data }, [data]); else postMessage({ id: m.id, odpoved });
  } catch (e) {
    postMessage({ id: m.id, chybaVolani: String(e).split("\n").slice(-3).join("\n") });
  }
}

onmessage = async (ev) => {
  await hotovo;
  if (!py) return;
  if (ev.data.volani) return volej(ev.data);
  const { vykres, pravidla, seznam, meritko, vestavena, nastaveni } = ev.data;
  try {
    postMessage({ stav: "Kontroluji výkres…", prace: true });
    const pv = zapis(vykres);
    let pp = zapis(pravidla);
    if (!pp && vestavena) {
      const r = await fetch(vestavena);
      pp = zapis({ nazev: vestavena.split("/").pop(), data: await r.arrayBuffer() });
    }
    const ps = zapis(seznam);
    const api = py.pyimport("kontrola.web_api");
    const json = api.zkontroluj(pv, pp, ps, meritko || null, nastaveni || null);
    postMessage({ vysledek: json });
  } catch (e) {
    postMessage({ chyba: String(e).split("\n").slice(-3).join("\n") });
  }
};
