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
