"""Geometrické porovnání výkresu s PDF od učitele (vektorové PDF z MicroStationu).

1. Z PDF se vezmou čáry (vektory) a texty s polohou na stránce.
2. PDF se samo umístí do souřadnic výkresu: popisy, které jsou v PDF i ve výkresu jen jednou
   (čísla bodů, výšky, názvy), dají dvojice bodů → podobnostní transformace (RANSAC), pak se
   zpřesní přiložením lomových bodů čar PDF na čáry výkresu (ICP).
3. Porovná se kresba: čáry z PDF, které ve výkresu nejsou (chybí), a čáry výkresu, které v PDF
   nejsou (navíc). Slouží jen ke kontrole – do výkresu se nic nepřenáší.

Sken (obrázek bez vektorů) porovnat nejde.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Point

from ..model import Drawing, GeomType


@dataclass
class PdfPorovnani:
    ok: bool
    zprava: str
    shod_popisu: int = 0
    meritko: float | None = None  # m výkresu na 1 bod PDF
    presnost: float | None = None  # medián odchylky po umístění [m]
    tolerance: float = 0.0
    pokryti_pdf: float = 0.0  # podíl kresby PDF, která ve výkresu je
    pokryti_vykresu: float = 0.0
    chybi: list = field(default_factory=list)  # LineString v souřadnicích výkresu (je v PDF, ve výkresu ne)
    navic: list = field(default_factory=list)  # (Feature, LineString) – je ve výkresu, v PDF ne
    pdf_cary: list = field(default_factory=list)  # celá kresba PDF v souřadnicích výkresu (podklad)


# ---------------------------------------------------------------- čtení PDF
def _pdf_content(path: str | Path, page_no: int = 0):
    import pdfplumber
    lines, words = [], []
    with pdfplumber.open(path) as pdf:
        pg = pdf.pages[page_no]
        H = float(pg.height)
        for obj in list(pg.lines) + list(pg.curves):
            pts = obj.get("pts") or []
            pts = [(float(x), H - float(y)) for x, y in pts]
            if len(pts) >= 2:
                lines.append(pts)
        for r in pg.rects:
            x0, x1, top, bottom = float(r["x0"]), float(r["x1"]), float(r["top"]), float(r["bottom"])
            if (x1 - x0) * (bottom - top) > 0.25 * float(pg.width) * H:
                continue  # rám stránky
            lines.append([(x0, H - top), (x1, H - top), (x1, H - bottom), (x0, H - bottom), (x0, H - top)])
        for w in pg.extract_words(extra_attrs=["size"]):
            words.append((w["text"].strip(), (float(w["x0"]) + float(w["x1"])) / 2,
                          H - (float(w["top"]) + float(w["bottom"])) / 2))
    return lines, words


def _drawing_texts(d: Drawing):
    out = defaultdict(list)
    for f in d.features:
        if f.geom_type == GeomType.TEXT and f.text and f.geometry is not None and f.geometry.geom_type == "Point":
            h = max(f.text_height or 0.0, 0.0)
            w = len(f.text.strip()) * h * 0.6 * (f.width_factor or 1.0)
            a = math.radians(f.rotation or 0.0)
            # střed textu (PDF dává střed slova) – přibližně podle zarovnání
            dx = {0: w / 2, 1: 0.0, 2: -w / 2}.get(f.halign, w / 2)
            dy = {0: h / 2, 1: h / 2, 2: 0.0, 3: -h / 2}.get(f.valign, h / 2)
            x = f.geometry.x + dx * math.cos(a) - dy * math.sin(a)
            y = f.geometry.y + dx * math.sin(a) + dy * math.cos(a)
            out[f.text.strip()].append((x, y))
    return out


# ---------------------------------------------------------------- transformace
def _similarity(src: np.ndarray, dst: np.ndarray):
    """Podobnostní transformace (Umeyama) src → dst: vrací (s, R, t)."""
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    cov = b.T @ a / len(src)
    U, S, Vt = np.linalg.svd(cov)
    D = np.eye(2)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[1, 1] = -1
    R = U @ D @ Vt
    var = (a ** 2).sum() / len(src)
    s = float(np.trace(np.diag(S) @ D) / var) if var > 0 else 1.0
    t = md - s * R @ ms
    return s, R, t


def _apply(T, pts: np.ndarray) -> np.ndarray:
    s, R, t = T
    return (s * (R @ pts.T)).T + t


def _register_labels(words, dtexts, tol: float):
    pw = defaultdict(list)
    for t, x, y in words:
        pw[t].append((x, y))
    common = [t for t in dtexts if len(t) >= 2 and len(dtexts[t]) == 1 and len(pw.get(t, [])) == 1]
    if len(common) < 3:
        return None, 0
    src = np.array([pw[t][0] for t in common], dtype=float)
    dst = np.array([dtexts[t][0] for t in common], dtype=float)
    rnd = random.Random(0)
    best, best_in = None, []
    n = len(common)
    for _ in range(min(600, n * (n - 1))):
        i, j = rnd.sample(range(n), 2)
        if np.hypot(*(src[i] - src[j])) < 1e-6:
            continue
        T = _similarity(src[[i, j]], dst[[i, j]])
        err = np.hypot(*(_apply(T, src) - dst).T)
        inl = np.nonzero(err <= tol)[0]
        if len(inl) > len(best_in):
            best, best_in = T, inl
    if best is None or len(best_in) < 3:
        return None, len(best_in)
    return _similarity(src[best_in], dst[best_in]), len(best_in)


def _densify(pts: np.ndarray, step: float) -> np.ndarray:
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        L = float(np.hypot(*(b - a)))
        k = max(1, int(L / step))
        for i in range(1, k + 1):
            out.append(a + (b - a) * i / k)
    return np.array(out)


def _icp(T, pdf_lines, dgeom, tree, ext, iters: int = 8, max_d: float = 1.0):
    """Zpřesnění umístění: body čar PDF (jen v rozsahu výkresu) se přiloží k nejbližší čáře výkresu."""
    samples = np.concatenate([np.asarray(p, dtype=float) for p in pdf_lines]) if pdf_lines else np.empty((0, 2))
    inside = shapely.contains_xy(ext, *_apply(T, samples).T) if len(samples) else np.zeros(0, bool)
    samples = samples[inside]
    if len(samples) > 20000:
        samples = samples[:: len(samples) // 20000 + 1]
    if len(samples) < 10:
        return T, None
    med = None
    for _ in range(iters):
        q = _apply(T, samples)
        pts = shapely.points(q)
        near = shapely.shortest_line(pts, dgeom[tree.nearest(pts)])
        tgt = np.array([ln.coords[1] for ln in near])
        d = np.hypot(*(tgt - q).T)
        m = d <= max_d
        if m.sum() < 10:
            break
        med = float(np.median(d[m]))
        T = _similarity(samples[m], tgt[m])  # z původních bodů PDF na nejbližší body výkresu
        max_d = max(med * 4, 0.05)
    return T, med


# ---------------------------------------------------------------- porovnání
def compare_pdf(path: str | Path, drawing: Drawing, tol: float | None = None) -> PdfPorovnani:
    try:
        lines, words = _pdf_content(path)
    except Exception as exc:  # noqa: BLE001 – poškozené PDF
        return PdfPorovnani(False, f"PDF nelze přečíst: {exc}")
    if len(lines) < 5:
        return PdfPorovnani(False, "PDF neobsahuje vektorovou kresbu (je to sken nebo obrázek) – porovnat jde "
                                   "jen vizuálně.")
    feats = [f for f in drawing.features if f.geom_type in (GeomType.LINIE, GeomType.POLYGON)
             and f.geometry is not None and not f.geometry.is_empty]
    if not feats:
        return PdfPorovnani(False, "Výkres nemá čáry k porovnání.")
    dgeom = np.array([f.geometry.boundary if f.geom_type == GeomType.POLYGON else f.geometry for f in feats],
                     dtype=object)
    tree = shapely.STRtree(dgeom)
    dtexts = _drawing_texts(drawing)
    T, n = None, 0
    for lab_tol in (1.5, 3.0, 6.0):
        T, n = _register_labels(words, dtexts, lab_tol)
        if T is not None:
            break
    if T is None:
        return PdfPorovnani(False, f"PDF se nepodařilo umístit na výkres – shoduje se jen {n} popisů (potřeba "
                                   "aspoň 3 stejná čísla bodů / popisy v PDF i ve výkresu).", n)
    ext = shapely.box(*shapely.total_bounds(dgeom)).buffer(2.0)
    T, med = _icp(T, lines, dgeom, tree, ext)
    scale = T[0]
    if tol is None:  # ~ tloušťka čáry v PDF a přesnost umístění
        tol = min(max(0.1, 3.0 * (med or 0.05), scale * 0.6), 1.0)
    pdf_ls = []
    for p in lines:
        q = _apply(T, np.asarray(p, dtype=float))
        ls = LineString(q)
        if ls.length > 0 and ls.intersects(ext):
            pdf_ls.append(ls.intersection(ext) if not ext.contains(ls) else ls)
    if not pdf_ls:
        return PdfPorovnani(False, "Kresba PDF leží mimo výkres – PDF je nejspíš k jinému výkresu.", n)
    pdf_union = shapely.union_all(np.array(pdf_ls, dtype=object))
    dr_union = shapely.union_all(dgeom)
    pdf_buf = pdf_union.buffer(tol)
    dr_buf = dr_union.buffer(tol)
    missing = pdf_union.difference(dr_buf)
    ch = [g for g in _parts(missing) if g.length >= max(0.5, tol * 4)]
    ch = _merge(ch, tol)
    total_pdf = pdf_union.length or 1.0
    extra = []
    covered_len = 0.0
    total_dr = 0.0
    for f, g in zip(feats, dgeom):
        out_part = g.difference(pdf_buf)
        total_dr += g.length
        covered_len += g.length - out_part.length
        if out_part.length >= max(0.5, tol * 4) and out_part.length >= 0.5 * g.length:
            extra.append((f, out_part))
    res = PdfPorovnani(True, "", n, scale, med, tol,
                       1.0 - sum(g.length for g in _parts(missing)) / total_pdf,
                       covered_len / total_dr if total_dr else 0.0, ch, extra, pdf_ls)
    res.zprava = (f"PDF umístěno podle {n} shodných popisů, přesnost {fmt(med)}; kresby z PDF je ve výkresu "
                  f"{res.pokryti_pdf * 100:.0f} %, chybí {len(ch)} úseků, navíc {len(extra)} prvků.")
    return res


def fmt(v: float | None) -> str:
    return "?" if v is None else (f"{v * 100:.0f} cm" if v >= 0.01 else f"{v * 1000:.0f} mm")


def _parts(g) -> list:
    if g.is_empty:
        return []
    if isinstance(g, LineString):
        return [g]
    if isinstance(g, MultiLineString) or hasattr(g, "geoms"):
        return [x for x in g.geoms if isinstance(x, LineString)]
    return []


def _merge(parts: list, tol: float) -> list:
    """Slije kousky chybějící kresby, které na sebe navazují (jedna chybějící čára = jeden nález)."""
    if not parts:
        return []
    merged = shapely.line_merge(shapely.union_all(np.array(parts, dtype=object)))
    return sorted(_parts(merged) or parts, key=lambda g: -g.length)


def point_on(g) -> Point:
    return g.interpolate(0.5, normalized=True)
