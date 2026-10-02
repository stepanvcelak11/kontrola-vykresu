"""Rozhraní pro webovou verzi (Pyodide v prohlížeči): stejná kontrola jako v desktopové aplikaci, výsledek jako JSON.

Nic se neodesílá na server – výkres, pravidla a seznam souřadnic se zapíšou do paměťového souborového systému
prohlížeče a zpracují se tam. Modul nesmí importovat Qt ani jiné desktopové knihovny.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def _nahrady_shapely() -> None:
    """V Pyodide (WebAssembly) padá vektorová funkce shapely.get_num_points / get_point („function signature
    mismatch“) – nahradí se stejným výpočtem po prvcích. Na desktopu se nic nemění."""
    import numpy as np
    import shapely

    def get_num_points(geometry, **_kw):
        if isinstance(geometry, np.ndarray):
            return np.array([len(g.coords) if g is not None and hasattr(g, "coords") else 0 for g in geometry.ravel()],
                            dtype=int).reshape(geometry.shape)
        return len(geometry.coords) if geometry is not None and hasattr(geometry, "coords") else 0

    def get_point(geometry, index, **_kw):
        from shapely.geometry import Point

        def jeden(g):
            if g is None or not hasattr(g, "coords"):
                return None
            c = list(g.coords)
            try:
                return Point(c[index])
            except IndexError:
                return None
        if isinstance(geometry, np.ndarray):
            out = np.empty(geometry.shape, dtype=object)
            for i, g in np.ndenumerate(geometry):
                out[i] = jeden(g)
            return out
        return jeden(geometry)

    shapely.get_num_points = get_num_points
    shapely.get_point = get_point


if sys.platform == "emscripten":
    _nahrady_shapely()

from .checks.base import Severity
from .config import Config
from .io.dxf_loader import load_drawing
from .rules import RuleSet
from .runner import run_checks

TABULKY = (".xlsx", ".xlsm", ".xls", ".csv", ".ods", ".tsv")
DOKUMENTY = (".doc", ".docx", ".odt", ".rtf")


def nacti_pravidla(cesta: str | None, meritko: int | None = None) -> tuple[RuleSet, list[str]]:
    """Pravidla z YAML, tabulky Směrnice (xls/xlsx/csv/ods) nebo Směrnice ve Wordu. Vrací (pravidla, poznámky)."""
    if not cesta:
        return RuleSet(), []
    p = Path(cesta)
    s = p.suffix.lower()
    if s in (".yaml", ".yml"):
        return RuleSet.load(p), []
    if s in TABULKY:
        from .importer.table import generate_rules, import_table
        td, hi, mapping = import_table(p)
        res = generate_rules(td.rows, hi, mapping, source=p.name)
        pozn = [res.summary()] + res.errors[:5] + res.warnings[:5]
        rs = res.rules
        if meritko and not rs.meritko:
            rs.meritko = meritko
        return rs, pozn
    if s in DOKUMENTY:
        from .importer.dokument import _doc_text
        from .importer.smernice_objekty import nacti_pravidla as z_textu
        from .importer.smernice_objekty import prevod_meritka
        if s == ".doc":
            text = _doc_text(p)
        else:
            from .importer.dokument import read_document
            dok = read_document(p)
            text = dok.text + "\n" + "\n".join("\x07".join(r) for t in dok.tabulky for r in t)
        rs = z_textu(text)
        if meritko and meritko != 1000:
            rs = prevod_meritka(rs, 1000, meritko)
        return rs, [f"Ze Směrnice vzniklo {len(rs.pravidla)} pravidel."]
    raise ValueError(f"Pravidla {p.name}: podporované jsou YAML, tabulka Směrnice (xls, xlsx, csv, ods) a Word.")


def _souradnice(g, tol: float) -> list:
    """Geometrie Shapely → seznam čar [[x, y, x, y, …], …] zjednodušených na ``tol`` (pro kreslení)."""
    t = g.geom_type
    if t == "Point":
        return []
    if t in ("LineString", "LinearRing"):
        gg = g.simplify(tol) if tol > 0 and len(g.coords) > 8 else g
        return [[round(v, 3) for xy in gg.coords for v in xy[:2]]]
    if t == "Polygon":
        out = _souradnice(g.exterior, tol)
        for i in g.interiors:
            out += _souradnice(i, tol)
        return out
    if hasattr(g, "geoms"):
        out = []
        for q in g.geoms:
            out += _souradnice(q, tol)
        return out
    return []


def _barva(rgb) -> str:
    try:
        r, g, b = (int(c) for c in rgb)
    except (TypeError, ValueError):
        return "#ffffff"
    if r < 40 and g < 40 and b < 40:  # černá na tmavém pozadí → bílá (jako MicroStation)
        r = g = b = 255
    return f"#{r:02x}{g:02x}{b:02x}"


def kresba(d, max_prvku: int = 60000) -> dict:
    b = d.bounds()
    sirka = (b[2] - b[0]) if b else 1.0
    tol = max(sirka, 1.0) / 4000.0
    cary, body, texty = [], [], []
    for f in d.features[:max_prvku]:
        g = f.geometry
        if g is None or g.is_empty:
            continue
        c = _barva(f.color_rgb)
        if f.geom_type.value == "text" and f.text:
            texty.append({"x": round(g.x, 3), "y": round(g.y, 3), "t": f.text[:80], "h": round(f.text_height, 3),
                          "r": round(f.rotation, 2), "c": c, "l": f.layer})
        elif g.geom_type == "Point":
            body.append([round(g.x, 3), round(g.y, 3), c, f.dxftype == "INSERT"])
        else:
            for s in _souradnice(g, tol):
                cary.append({"p": s, "c": c, "w": round(f.lineweight or 0.0, 2), "l": f.layer})
    return {"bounds": list(b) if b else None, "cary": cary, "body": body, "texty": texty}


def zkontroluj(vykres: str, pravidla: str | None = None, seznam: str | None = None,
               meritko: int | None = None) -> str:
    """Kontrola výkresu → JSON: chyby (s návodem), skóre, poznámky, kresba pro plátno."""
    from .navody import navod
    from .skore import compute_score
    d = load_drawing(vykres)
    rs, pozn = nacti_pravidla(pravidla, meritko)
    cfg = Config()
    if seznam:
        cfg.seznam_souradnic = seznam
    res = run_checks(d, rs, cfg)
    sk = compute_score(res.issues, bool(rs.pravidla))
    chyby = []
    for i, iss in enumerate(res.issues):
        try:
            nav = navod(iss)
        except Exception:  # noqa: BLE001 – návod je doplněk, kontrola musí doběhnout
            nav = ""
        x = iss.x if iss.x is not None and math.isfinite(iss.x) else None
        y = iss.y if iss.y is not None and math.isfinite(iss.y) else None
        chyby.append({"id": i, "zavaznost": iss.severity.value if isinstance(iss.severity, Severity) else str(iss.severity),
                      "kontrola": iss.check_name, "zprava": iss.message, "x": x, "y": y, "vrstva": iss.layer or "",
                      "navod": nav})
    return json.dumps({
        "soubor": Path(vykres).name, "prvku": len(d.features), "vrstev": len(d.layers),
        "pravidel": len(rs.pravidla), "skore": {"hodnota": sk.hodnota, "popis": sk.popis, "barva": sk.barva},
        "varovani": list(d.warnings) + pozn, "chyby": chyby, "kresba": kresba(d),
    }, ensure_ascii=False)


# ------------------------------------------------------------------ Výpočty (Groma) ve webové verzi
def _body_json(body) -> list[dict]:
    return [{"c": b.cislo, "y": b.y, "x": b.x, "z": b.z, "kod": b.kod or "", "kk": b.kvalita,
             "pozn": b.poznamka or ""} for b in body]


def _seznam(body_json: str):
    from .geodezie.body import Bod, SeznamBodu
    s = SeznamBodu()
    for d in json.loads(body_json or "[]"):
        try:
            s.body.append(Bod(str(d["c"]), float(d["y"]), float(d["x"]),
                              None if d.get("z") in (None, "") else float(d["z"]),
                              d.get("kod") or "", d.get("kk"), d.get("pozn") or ""))
        except (KeyError, TypeError, ValueError):
            continue
    return s


def nacti_seznam(cesta: str) -> str:
    """Seznam souřadnic ze souboru (txt, csv, Groma, Kokeš…) → JSON {body, varovani, format}."""
    from .geodezie.formaty import nacti_soubor
    body, var, fmt = nacti_soubor(cesta)
    return json.dumps({"body": _body_json(body), "varovani": var[:50],
                       "format": " ".join(fmt.sloupce)}, ensure_ascii=False)


def seznam_text(body_json: str, oddelovac: str = " ") -> str:
    """Seznam bodů do textu (zarovnané sloupce jako Groma, nebo CSV se středníkem)."""
    from .geodezie.formaty import zapis_text
    s = _seznam(body_json)
    sl = ["cislo", "y", "x", "z", "kod"] if any(b.kod for b in s.body) else ["cislo", "y", "x", "z"]
    return zapis_text(s.body, sl, oddelovac, hlavicka=oddelovac != " ")


def ulohy() -> str:
    """Popis všech úloh (pole formuláře) pro webový formulář."""
    from .geodezie.ulohy import ULOHY
    return json.dumps([{"nazev": n, "popis": p, "pole": [
        {"key": f.key, "label": f.label, "typ": f.typ, "vychozi": f.vychozi, "volby": list(f.volby),
         "napoveda": f.napoveda} for f in pole]} for n, p, pole, _fn in ULOHY], ensure_ascii=False)


def spocti(index: int, body_json: str, hodnoty_json: str) -> str:
    """Výpočet úlohy → JSON {protokol, nove} nebo {chyba} (chyba vstupu srozumitelně)."""
    from .geodezie.ulohy import ULOHY, ChybaVstupu
    s = _seznam(body_json)
    _n, _p, _pole, fn = ULOHY[int(index)]
    try:
        v = fn(s, json.loads(hodnoty_json or "{}"))
    except ChybaVstupu as e:
        return json.dumps({"chyba": str(e)}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 – výpočet nesmí shodit stránku
        return json.dumps({"chyba": f"Výpočet se nepovedl: {e}"}, ensure_ascii=False)
    return json.dumps({"protokol": "\n".join(v.protokol), "nove": _body_json(v.nove)}, ensure_ascii=False)


def polarni(zapisnik: str, body_json: str) -> str:
    """Polární metoda dávkou ze zápisníku (.zap Gromy nebo GSI) a daných bodů → protokol jako v Gromě."""
    from .checks.seznam import ListPoint
    from .geodezie import zapisnik as Z
    from .geodezie.protokol import protokol_polarni
    from .vypocet import compute
    s = _seznam(body_json)
    dane = [ListPoint(b.cislo, b.y, b.x, b.z) for b in s.body]
    if not dane:
        return json.dumps({"chyba": "Nejdřív načtěte seznam souřadnic s danými body."}, ensure_ascii=False)
    try:
        stanoviska = Z.nacti(zapisnik, {b.cislo for b in s.body})
        if not stanoviska:
            return json.dumps({"chyba": "V zápisníku nejsou žádná stanoviska."}, ensure_ascii=False)
        upoz = Z.zkontroluj(stanoviska)
        st = Z.pro_vypocet(stanoviska)
        res = compute(st, dane)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"chyba": f"Výpočet se nepovedl: {e}"}, ensure_ascii=False)
    from .geodezie.body import Bod
    nove = [Bod(p.bod, p.y, p.x, p.z, poznamka=f"polárně z {p.stanovisko}") for p in res.body if not p.kontrolni]
    text = protokol_polarni(res, st, dane, soubor_mereni=Path(zapisnik).name)
    return json.dumps({"protokol": text, "nove": _body_json(nove), "upozorneni": upoz[:10],
                       "stanovisek": len(stanoviska)}, ensure_ascii=False)
