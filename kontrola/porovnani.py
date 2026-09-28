"""Porovnání dvou verzí výkresu: co přibylo, co zmizelo, co se změnilo.

Prvky se párují podle geometrie (zaokrouhlené na milimetry, bez ohledu na směr čáry a počáteční
bod plochy). Stejná geometrie s jinými atributy = „změněno“. Zbylé dvojice na stejné vrstvě,
které jsou blízko sebe, se považují za „upravený tvar“ (posunutý vrchol, prodloužená čára).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

import shapely
from shapely.strtree import STRtree

from .checks.base import fmt_num
from .model import Drawing, Feature, GeomType

PRIDANO, ODEBRANO, ZMENENO, UPRAVENO = "přidáno", "odebráno", "změněny atributy", "upravený tvar"
DRUHY = (PRIDANO, ODEBRANO, UPRAVENO, ZMENENO)


@dataclass
class Zmena:
    druh: str
    vrstva: str
    popis: str
    x: float
    y: float
    old: Feature | None = None
    new: Feature | None = None


def _what(f: Feature) -> str:
    if f.geom_type == GeomType.TEXT:
        return f"text „{(f.text or '').strip()[:30]}“"
    if f.block_name:
        return f"buňka {f.block_name}"
    return {GeomType.BOD: "bod", GeomType.LINIE: "čára", GeomType.POLYGON: "plocha"}[f.geom_type]


def _geom_key(f: Feature, grid: float) -> bytes:
    g = f.geometry
    if g is None or g.is_empty:
        return b""
    try:
        g = shapely.set_precision(g, grid).normalize()
    except Exception:  # noqa: BLE001 – neplatná geometrie: porovnat aspoň obálku
        return repr(tuple(round(v / grid) for v in g.bounds)).encode()
    return f.geom_type.value.encode() + g.wkb


_ATTRS = (("vrstva", lambda f: f.layer), ("barva", lambda f: f.color_aci if f.color_aci is not None else f.color_rgb),
          ("styl", lambda f: (f.linetype or "").upper()), ("tloušťka", lambda f: round(f.lineweight, 2)),
          ("měřítko stylu", lambda f: round(f.ltscale, 3)), ("text", lambda f: f.text or ""),
          ("výška textu", lambda f: round(f.text_height, 3)), ("písmo", lambda f: f.font or ""),
          ("buňka", lambda f: f.block_name or ""), ("natočení", lambda f: round(f.rotation or 0.0, 1)))


def attr_diff(a: Feature, b: Feature) -> list[str]:
    out = []
    for name, get in _ATTRS:
        va, vb = get(a), get(b)
        if va != vb:
            if isinstance(va, float):
                va, vb = fmt_num(va, 3), fmt_num(vb, 3)
            out.append(f"{name} {va} → {vb}")
    return out


def _pos(f: Feature) -> tuple[float, float]:
    g = f.geometry
    if g is None or g.is_empty:
        return 0.0, 0.0
    p = g.representative_point() if g.geom_type != "Point" else g
    return p.x, p.y


def compare(old: Drawing, new: Drawing, grid: float = 0.001, shape_dist: float = 1.0) -> list[Zmena]:
    """Vrátí seznam změn mezi ``old`` a ``new`` (nejdřív přidané, odebrané, upravené, pak atributy)."""
    pool: dict[bytes, list[Feature]] = defaultdict(list)
    for f in old.features:
        pool[_geom_key(f, grid)].append(f)
    changes: list[Zmena] = []
    added: list[Feature] = []
    for f in new.features:
        cands = pool.get(_geom_key(f, grid))
        if not cands:
            added.append(f)
            continue
        best = next((o for o in cands if not attr_diff(o, f)), None)
        if best is None:
            best = next((o for o in cands if o.layer == f.layer), cands[0])
            x, y = _pos(f)
            changes.append(Zmena(ZMENENO, f.layer, f"Změněno: {_what(f)} – " + ", ".join(attr_diff(best, f)),
                                 x, y, best, f))
        cands.remove(best)
    removed = [o for lst in pool.values() for o in lst]

    # upravený tvar: odebraný a přidaný prvek stejného druhu na stejné vrstvě těsně vedle sebe
    used: set[int] = set()
    if removed and added:
        geoms = [o.geometry for o in removed]
        tree = STRtree(geoms)
        rest_added = []
        for f in added:
            match = None
            if f.geometry is not None and not f.geometry.is_empty:
                for k in tree.query(f.geometry, predicate="dwithin", distance=shape_dist):
                    o = removed[int(k)]
                    if int(k) in used or o.layer != f.layer or o.geom_type != f.geom_type:
                        continue
                    if o.geom_type == GeomType.TEXT and (o.text or "") != (f.text or ""):
                        continue
                    try:
                        h = o.geometry.hausdorff_distance(f.geometry)
                    except Exception:  # noqa: BLE001
                        continue
                    if h <= max(shape_dist * 3, 0.2 * max(o.geometry.length, 1.0)):
                        match = int(k)
                        break
            if match is None:
                rest_added.append(f)
                continue
            used.add(match)
            o = removed[match]
            x, y = _pos(f)
            det = []
            if f.geom_type in (GeomType.LINIE, GeomType.POLYGON):
                dl = f.geometry.length - o.geometry.length
                if abs(dl) >= grid:
                    det.append(f"délka {'+' if dl > 0 else ''}{fmt_num(dl, 3)} m")
                else:
                    det.append(f"posun až o {fmt_num(o.geometry.hausdorff_distance(f.geometry), 3)} m")
            elif f.geometry.geom_type == "Point":
                det.append(f"posun o {fmt_num(o.geometry.distance(f.geometry), 3)} m")
            det += attr_diff(o, f)
            changes.append(Zmena(UPRAVENO, f.layer, f"Upraveno: {_what(f)}"
                                 + (f" ({', '.join(det)})" if det else ""), x, y, o, f))
        added = rest_added
    for f in added:
        x, y = _pos(f)
        changes.append(Zmena(PRIDANO, f.layer, f"Přidáno: {_what(f)}", x, y, None, f))
    for k, o in enumerate(removed):
        if k in used:
            continue
        x, y = _pos(o)
        changes.append(Zmena(ODEBRANO, o.layer, f"Odebráno: {_what(o)}", x, y, o, None))
    order = {d: i for i, d in enumerate(DRUHY)}
    changes.sort(key=lambda z: (order[z.druh], z.vrstva.lower(), z.y, z.x))
    return changes


def summary(changes: list[Zmena]) -> str:
    if not changes:
        return "Výkresy jsou stejné – žádná změna."
    c = Counter(z.druh for z in changes)
    return ", ".join(f"{d}: {c[d]}" for d in DRUHY if c.get(d))
