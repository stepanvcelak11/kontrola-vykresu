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
            body.append([round(g.x, 3), round(g.y, 3), c, f.dxftype == "INSERT", f.layer])
        else:
            for s in _souradnice(g, tol):
                cary.append({"p": s, "c": c, "w": round(f.lineweight or 0.0, 2), "l": f.layer})
    return {"bounds": list(b) if b else None, "cary": cary, "body": body, "texty": texty}


_POSLEDNI: dict = {}  # poslední kontrola (výkres, pravidla, nastavení, chyby) – pro exporty a další nástroje
VYSTUP = Path("/out") if sys.platform == "emscripten" else Path(__import__("tempfile").gettempdir()) / "kv_web"


def _vystup(nazev: str) -> Path:
    VYSTUP.mkdir(parents=True, exist_ok=True)
    return VYSTUP / nazev


def _soubor(cesta: Path, **dalsi) -> str:
    """Odpověď se souborem ke stažení: worker ho přečte a pošle prohlížeči."""
    return json.dumps(dict(dalsi, soubor=str(cesta), nazev=cesta.name), ensure_ascii=False)


def kontroly() -> str:
    """Seznam kontrol pro výběr (jako Nastavení → Kontroly na desktopu)."""
    from .checks.base import REGISTRY
    cfg = Config()
    return json.dumps([{"id": k, "nazev": c.nazev or k, "skupina": c.skupina, "popis": c.popis,
                        "zapnuto": cfg.settings(k).zapnuto, "pravidla": c.potrebuje_pravidla}
                       for k, c in REGISTRY.items()], ensure_ascii=False)


def _config(nastaveni: dict | None) -> Config:
    cfg = Config()
    n = nastaveni or {}
    if n.get("tolerance"):
        cfg.tolerance = float(n["tolerance"])
    cfg.rozpracovany = bool(n.get("rozpracovany"))
    for cid in n.get("vypnute") or []:
        cfg.settings(cid).zapnuto = False
    for cid in n.get("zapnute") or []:
        cfg.settings(cid).zapnuto = True
    return cfg


def _vrstvy(d) -> list[dict]:
    from collections import Counter
    c = Counter(f.layer for f in d.features)
    return [{"nazev": k, "prvku": n} for k, n in sorted(c.items(), key=lambda kv: _klic_vrstvy(kv[0]))]


def _klic_vrstvy(n: str):
    import re
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", n) if t]


def zkontroluj(vykres: str, pravidla: str | None = None, seznam: str | None = None,
               meritko: int | None = None, nastaveni: str | None = None) -> str:
    """Kontrola výkresu → JSON: chyby (s návodem), skóre, poznámky, kresba pro plátno, hladiny."""
    from .navody import navod
    from .skore import compute_score
    d = load_drawing(vykres)
    rs, pozn = nacti_pravidla(pravidla, meritko)
    cfg = _config(json.loads(nastaveni) if nastaveni else None)
    if seznam:
        cfg.seznam_souradnic = seznam
    res = run_checks(d, rs, cfg)
    for i, iss in enumerate(res.issues, 1):
        iss.number = iss.number or i
    _POSLEDNI.clear()
    _POSLEDNI.update(d=d, rs=rs, cfg=cfg, issues=res.issues, vykres=vykres, pravidla=pravidla, seznam=seznam)
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
                      "kontrola": iss.check_name, "kid": iss.check_id, "zprava": iss.message, "x": x, "y": y,
                      "vrstva": iss.layer or "", "navod": nav})
    return json.dumps({
        "soubor": Path(vykres).name, "prvku": len(d.features), "vrstev": len(d.layers),
        "pravidel": len(rs.pravidla), "skore": {"hodnota": sk.hodnota, "popis": sk.popis, "barva": sk.barva},
        "varovani": list(d.warnings) + pozn, "chyby": chyby, "kresba": kresba(d), "vrstvy": _vrstvy(d),
    }, ensure_ascii=False)


def _potreba_kontroly():
    if not _POSLEDNI:
        raise ValueError("Nejdřív výkres zkontrolujte.")
    return _POSLEDNI


def export(druh: str) -> str:
    """Export výsledku kontroly: html (interaktivní protokol), pdf (protokol), oprava (seznam k opravě na tisk),
    xlsx, csv, dxf (výkres s kroužky chyb), log (seznam chyb jako MGEO)."""
    p = _potreba_kontroly()
    d, rs, issues = p["d"], p["rs"], p["issues"]
    zaklad = Path(p["vykres"]).stem
    if druh == "html":
        from .export.html_report import export_html
        out = export_html(issues, _vystup(f"{zaklad}_protokol.html"), drawing_name=Path(p["vykres"]).name,
                          has_rules=bool(rs.pravidla))
    elif druh == "pdf":
        from .export.pdf_report import export_pdf
        out = _vystup(f"{zaklad}_protokol.pdf")
        export_pdf(issues, out, drawing_name=Path(p["vykres"]).name, rules_count=len(rs.pravidla),
                   tolerance=p["cfg"].tolerance)
    elif druh == "oprava":
        from .export.pdf_report import export_checklist
        out = _vystup(f"{zaklad}_k_oprave.pdf")
        export_checklist([i for i in issues if i.state == "nová"], out, drawing_name=Path(p["vykres"]).name)
    elif druh == "xlsx":
        from .export.tables import export_xlsx
        out = _vystup(f"{zaklad}_chyby.xlsx")
        export_xlsx(issues, out, Path(p["vykres"]).name)
    elif druh == "csv":
        from .export.tables import export_csv
        out = _vystup(f"{zaklad}_chyby.csv")
        export_csv(issues, out)
    elif druh == "dxf":
        from .export.dxf_export import export_dxf
        out = _vystup(f"{zaklad}_chyby.dxf")
        export_dxf(d, issues, out)
    elif druh == "log":
        from .export.mgeo_log import export_mgeo_log
        out = export_mgeo_log(d, rs, issues, _vystup(f"{zaklad}.log"), rules_name=Path(p["pravidla"] or "").name,
                              tolerance=p["cfg"].tolerance)
    else:
        raise ValueError(f"Neznámý export {druh}.")
    return _soubor(Path(out))


def volby_opravy() -> str:
    from .repair import RepairOptions
    o = RepairOptions()
    return json.dumps([{"id": k, "popis": t, "zapnuto": bool(getattr(o, k))} for k, t in RepairOptions.LABELS.items()],
                      ensure_ascii=False)


def oprava(volby: str = "{}") -> str:
    """Automatická oprava (jako Oprava na desktopu) → opravený výkres DXF ke stažení + co se opravilo."""
    from .repair import RepairOptions, repair_drawing
    p = _potreba_kontroly()
    o = RepairOptions()
    for k, v in (json.loads(volby or "{}") or {}).items():
        if hasattr(o, k):
            setattr(o, k, bool(v))
    out = _vystup(f"{Path(p['vykres']).stem}_opraveno.dxf")
    rep = repair_drawing(p["d"], p["rs"], p["cfg"], out, o)
    return _soubor(out, text=rep.text(), podrobne=rep.details[:200], rucne=rep.skipped[:200], oprav=rep.total)


def porovnej(stary: str) -> str:
    """Porovnání se starší verzí výkresu: co přibylo, zmizelo a změnilo se (s polohou)."""
    from .porovnani import compare, summary
    p = _potreba_kontroly()
    zmeny = compare(load_drawing(stary), p["d"])
    return json.dumps({"souhrn": summary(zmeny), "zmeny": [
        {"druh": z.druh, "vrstva": z.vrstva, "popis": z.popis, "x": z.x, "y": z.y} for z in zmeny[:3000]]},
        ensure_ascii=False)


def protokol_ucitele(log: str) -> str:
    """Porovnání s protokolem od učitele (.log z MGEO / MicroStationu): co učitel našel a co program."""
    from .protokol_ucitele import compare_with_teacher, read_teacher_log
    p = _potreba_kontroly()
    prot = read_teacher_log(log)
    rows, souhrn = compare_with_teacher(prot, p["d"], p["rs"], p["issues"])
    return json.dumps({"souhrn": souhrn, "radky": [
        {"vrstva": r.vrstva, "co": r.popis, "ucitel": r.ucitel, "program": r.program} for r in rows]},
        ensure_ascii=False)


def predikce() -> str:
    """Odhad, co najde učitel (podle chyb programu)."""
    from .predikce import label, predict
    p = _potreba_kontroly()
    pr = predict(p["d"], p["rs"], p["issues"], cal={})
    return json.dumps({"verdikt": pr.verdikt, "barva": pr.barva, "atributy": pr.atributy, "topologie": pr.topologie,
                       "skupin": pr.skupin, "pozor": pr.pozor, "skupiny": [
                           {"co": label(g.klic), "program": g.program, "predpoved": g.predpoved,
                            "poznamka": g.poznamka, "vrstvy": g.vrstvy[:12]} for g in pr.skupiny]},
                      ensure_ascii=False)


def prvek_na(x: float, y: float, tol: float = 1.0) -> str:
    """Vlastnosti prvku nejblíž bodu (inspektor prvku jako na desktopu)."""
    from shapely.geometry import Point
    p = _potreba_kontroly()
    bod, nej, dmin = Point(x, y), None, tol
    for f in p["d"].features:
        g = f.geometry
        if g is None or g.is_empty:
            continue
        b = g.bounds
        if b[0] - tol > x or b[2] + tol < x or b[1] - tol > y or b[3] + tol < y:
            continue
        dd = g.distance(bod)
        if dd <= dmin:
            dmin, nej = dd, f
    if nej is None:
        return json.dumps({}, ensure_ascii=False)
    f = nej
    vl = {"Hladina": f.layer, "Typ": f.dxftype or f.geom_type.value, "Barva": _barva(f.color_rgb)}
    for nazev, attr in (("Číslo barvy", "color_aci"), ("Styl čáry", "linetype"), ("Tloušťka [mm]", "lineweight"),
                        ("Buňka", "block_name"), ("Text", "text"), ("Výška textu", "text_height"),
                        ("Natočení [°]", "rotation")):
        v = getattr(f, attr, None)
        if v not in (None, "", 0, 0.0):
            vl[nazev] = round(v, 3) if isinstance(v, float) else v
    for k, v in list((f.attributes or {}).items())[:12]:
        vl[f"Atribut {k}"] = v
    g = f.geometry
    if g.geom_type in ("LineString", "LinearRing"):
        vl["Délka"] = f"{g.length:.3f} m"
    elif g.geom_type == "Polygon":
        vl["Výměra"] = f"{g.area:.2f} m²"
        vl["Obvod"] = f"{g.length:.3f} m"
    elif g.geom_type == "Point":
        vl["Souřadnice"] = f"Y {-g.x:.2f}  X {-g.y:.2f}" if g.x < 0 and g.y < 0 else f"{g.x:.2f}, {g.y:.2f}"
    chyby = [i.message for i in p["issues"] if f.fid in (i.feature_ids or [])][:10]
    return json.dumps({"vlastnosti": {k: str(v) for k, v in vl.items()}, "chyby": chyby,
                       "obrys": _souradnice(g, 0)[:20]}, ensure_ascii=False)


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


def vrstevnice_dxf(body_json: str, hodnoty_json: str) -> str:
    """Vrstevnice (a popisy) ze seznamu bodů jako text DXF – souřadnice jako v MicroStationu (−Y, −X)."""
    import io

    import ezdxf

    from .cad import teren_cad as TC
    from .geodezie import teren as T
    h = json.loads(hodnoty_json or "{}")
    s = _seznam(body_json)
    cisla = set((h.get("body") or "").split())
    body = [(-b.y, -b.x, b.z) for b in s.body if b.z is not None and (not cisla or b.cislo in cisla)]

    def cislo(k, vych):
        t = str(h.get(k) or "").strip().replace(",", ".")
        return float(t) if t else vych
    try:
        m = T.model(body, cislo("interval", 1.0), max_strana=cislo("ms", None) or None, vyhladit=2)
    except ValueError as e:
        return json.dumps({"chyba": str(e)}, ensure_ascii=False)
    doc = ezdxf.new("R2000")
    TC.kresli(doc, doc.modelspace(), None, m, popis=True, vyska_textu=0.75)
    out = io.StringIO()
    doc.write(out)
    return json.dumps({"dxf": out.getvalue(), "souhrn": TC.souhrn(m)}, ensure_ascii=False)


# ------------------------------------------------------------------ zápisník (jako zápisník Gromy)
def _obs_json(o) -> dict:
    return {"bod": o.bod, "sd": o.sd, "vc": o.vc, "hz": o.hz, "z": o.z}


def _zap_json(stanoviska) -> list[dict]:
    return [{"bod": s.bod, "vp": s.vp, "orient": [_obs_json(o) for o in s.orient],
             "detail": [_obs_json(o) for o in s.detail]} for s in stanoviska]


def _zap(zap_json: str):
    from .vypocet import Obs, Station
    out = []
    for s in json.loads(zap_json or "[]"):
        st = Station(str(s.get("bod") or "").strip(), float(s.get("vp") or 0))
        for k in ("orient", "detail"):
            for o in s.get(k) or []:
                try:
                    getattr(st, k).append(Obs(str(o["bod"]).strip(), float(o["sd"]), float(o.get("vc") or 0),
                                              float(o["hz"]), float(o["z"])))
                except (KeyError, TypeError, ValueError):
                    continue
        if st.bod:
            out.append(st)
    return out


def nacti_zapisnik(cesta: str, body_json: str = "[]") -> str:
    """Zápisník .zap (Groma) nebo GSI (Leica) → stanoviska a záměry k úpravě, upozornění na zjevné chyby."""
    from .geodezie import zapisnik as Z
    st = Z.nacti(cesta, {b.cislo for b in _seznam(body_json).body})
    return json.dumps({"stanoviska": _zap_json(st), "upozorneni": Z.zkontroluj(st)[:30]}, ensure_ascii=False)


def zapisnik_soubor(zap_json: str, druh: str = "zap", nazev: str = "zapisnik") -> str:
    """Zápisník ke stažení: .zap (čte Groma i tato aplikace) nebo GSI-16."""
    from .geodezie import zapisnik as Z
    st = _zap(zap_json)
    if druh == "gsi":
        from .geodezie.gsi import zapis_gsi
        out = _vystup(f"{nazev}.gsi")
        out.write_text(zapis_gsi(st), encoding="ascii", errors="replace")
    else:
        out = _vystup(f"{nazev}.zap")
        out.write_text(Z.zapis_zap(st, nazev), encoding="cp1250", errors="replace")
    return _soubor(out)


def polarni_zapisnik(zap_json: str, body_json: str, nazev_mereni: str = "") -> str:
    """Polární metoda dávkou ze (upraveného) zápisníku – protokol jako v Gromě."""
    from .checks.seznam import ListPoint
    from .geodezie import zapisnik as Z
    from .geodezie.body import Bod
    from .geodezie.protokol import protokol_polarni
    from .vypocet import compute
    s = _seznam(body_json)
    dane = [ListPoint(b.cislo, b.y, b.x, b.z) for b in s.body]
    stanoviska = _zap(zap_json)
    if not dane:
        return json.dumps({"chyba": "Nejdřív načtěte seznam souřadnic s danými body."}, ensure_ascii=False)
    if not stanoviska:
        return json.dumps({"chyba": "Zápisník je prázdný."}, ensure_ascii=False)
    try:
        st = Z.pro_vypocet(stanoviska)
        res = compute(st, dane)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"chyba": f"Výpočet se nepovedl: {e}"}, ensure_ascii=False)
    nove = [Bod(p.bod, p.y, p.x, p.z, poznamka=f"polárně z {p.stanovisko}") for p in res.body if not p.kontrolni]
    text = protokol_polarni(res, st, dane, soubor_mereni=nazev_mereni)
    return json.dumps({"protokol": text, "nove": _body_json(nove), "upozorneni": Z.zkontroluj(stanoviska)[:10],
                       "stanovisek": len(stanoviska)}, ensure_ascii=False)


def vyrovnani(zap_json: str, body_json: str, smer_cc: float = 10.0, delka_mm: float = 3.0, ppm: float = 2.0) -> str:
    """Vyrovnání sítě MNČ ze zápisníku (směry a délky), pevné body ze seznamu souřadnic."""
    from .geodezie import zapisnik as Z
    from .geodezie.body import Bod
    s = _seznam(body_json)
    try:
        v, text = Z.vyrovnani_site(_zap(zap_json), s.body, float(smer_cc), float(delka_mm), float(ppm))
    except ValueError as e:
        return json.dumps({"chyba": str(e)}, ensure_ascii=False)
    pevne = {b.cislo for b in s.body}
    nove = [Bod(c, y, x, poznamka="vyrovnání MNČ") for c, (y, x) in v.souradnice.items() if c not in pevne]
    return json.dumps({"protokol": text, "nove": _body_json(nove),
                       "souhrn": f"Vyrovnáno {len(v.souradnice)} bodů, σ0 = {v.sigma0:.2f}, nadbytečných měření "
                                 f"{v.redundance}."}, ensure_ascii=False)


def kontrola_vypoctu(student: str, zap_json: str, body_json: str, tol_xy: float = 0.01, tol_z: float = 0.01) -> str:
    """Kontrola výpočtu souřadnic: vlastní výpočet polární metodou ze zápisníku a porovnání se seznamem
    souřadnic studenta (Groma) – rozdíly po bodech a pravděpodobné příčiny."""
    from .checks.seznam import ListPoint, read_point_list
    from .geodezie import zapisnik as Z
    from .vypocet import compare, compute, diagnose, text_report
    known = [ListPoint(b.cislo, b.y, b.x, b.z) for b in _seznam(body_json).body]
    st = _zap(zap_json)
    if not known or not st:
        return json.dumps({"chyba": "Potřebuji zápisník a dané body v seznamu souřadnic."}, ensure_ascii=False)
    res = compute(Z.pro_vypocet(st), known)
    stud = read_point_list(student)
    bad, rows = compare(res, stud, float(tol_xy), float(tol_z), known=known)
    diag = diagnose(res, rows, float(tol_xy), float(tol_z))
    return json.dumps({"protokol": text_report(res, rows, bad, diag), "rozdilu": len(bad), "bodu": len(rows),
                       "priciny": diag}, ensure_ascii=False)


# ------------------------------------------------------------------ seznam souřadnic: kontroly a porovnání
def duplicity(body_json: str, tol: float = 0.01) -> str:
    s = _seznam(body_json)
    d = s.duplicity(float(tol))
    return json.dumps({"pocet": len(d), "text": "\n".join(x.popis() for x in d) or "Žádné duplicity.",
                       "cisla": sorted({b.cislo for x in d for b in x.body})}, ensure_ascii=False)


def porovnej_seznamy(druhy: str, body_json: str, kk: int = 3) -> str:
    """Porovnání seznamu souřadnic s jiným seznamem (např. Groma vs. vlastní výpočet): ΔY, ΔX, Δp, ΔZ a mezní
    polohová odchylka podle kódu kvality."""
    from .geodezie.formaty import nacti_soubor
    from .geodezie.vypocty import porovnani_seznamu
    a = _seznam(body_json).body
    b, _var, _f = nacti_soubor(druhy)
    rozd, jen_a, jen_b = porovnani_seznamu(a, b, int(kk))
    r = [f"POROVNÁNÍ SEZNAMŮ SOUŘADNIC (kód kvality {kk})", "=" * 44,
         f"{'Bod':<16}{'dY':>9}{'dX':>9}{'dp':>9}{'dZ':>9}{'mez':>8}  vyhovuje"]
    for x in rozd:
        dz = f"{x.dz:+.3f}" if x.dz is not None else "–"
        mez = f"{x.mezni:.3f}" if x.mezni is not None else "–"
        ok = "–" if x.vyhovuje is None else ("ano" if x.vyhovuje else "NE")
        r.append(f"{x.cislo:<16}{x.dy:+9.3f}{x.dx:+9.3f}{x.dp:9.3f}{dz:>9}{mez:>8}  {ok}")
    if jen_a:
        r += ["", f"Jen v tomto seznamu ({len(jen_a)}): " + ", ".join(jen_a[:80])]
    if jen_b:
        r += ["", f"Jen v druhém seznamu ({len(jen_b)}): " + ", ".join(jen_b[:80])]
    nevyh = sum(1 for x in rozd if x.vyhovuje is False)
    return json.dumps({"protokol": "\n".join(r), "souhrn": f"Porovnáno {len(rozd)} bodů, nevyhovuje {nevyh}."},
                      ensure_ascii=False)


def protokol_pdf(text: str, nazev: str = "protokol") -> str:
    """Výpočetní protokol (text) do PDF – neproporcionální písmo, hlavička na každé stránce."""
    from .geodezie.protokol import protokol_pdf as pdf
    out = _vystup(f"{nazev}.pdf")
    pdf(text, out, nazev=nazev)
    return _soubor(out)


# ------------------------------------------------------------------ QTrig (zakázky ze zálohy účtu)
_QTRIG: dict = {}


def qtrig_zakazky(zaloha_b64: str) -> str:
    """Záloha účtu QTrig (gzip + base64, jak ji vrací server) → zakázky s počtem bodů."""
    from . import qtrig as Q
    try:
        zak = Q.zakazky_ze_zalohy(Q.rozbal_zalohu_uctu(zaloha_b64))
    except Q.ChybaQTrig as e:
        return json.dumps({"chyba": str(e)}, ensure_ascii=False)
    _QTRIG.clear()
    _QTRIG.update({z["key"]: z for z in zak})
    return json.dumps([{"key": z["key"], "name": z["name"], "n": len(z["body"])} for z in zak], ensure_ascii=False)


def qtrig_body(klic: str) -> str:
    """Body zvolené zakázky v S-JTSK (stejný převod jako v QTrig)."""
    z = _QTRIG.get(klic)
    if z is None:
        return json.dumps({"chyba": "Zakázka v záloze není – přihlaste se znovu."}, ensure_ascii=False)
    return json.dumps({"nazev": z["name"], "body": _body_json(z["body"])}, ensure_ascii=False)
