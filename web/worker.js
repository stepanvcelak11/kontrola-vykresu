// Výpočetní vlákno webové verze: Python (Pyodide) s jádrem Kontroly výkresu. Soubory zůstávají v prohlížeči.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.2/full/";
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

onmessage = async (ev) => {
  await hotovo;
  if (!py) return;
  const { vykres, pravidla, seznam, meritko, vestavena } = ev.data;
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
    const json = api.zkontroluj(pv, pp, ps, meritko || null);
    postMessage({ vysledek: json });
  } catch (e) {
    postMessage({ chyba: String(e).split("\n").slice(-3).join("\n") });
  }
};
