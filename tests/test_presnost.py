"""Přesnost kontrol: do skutečného výkresu ze zadání se vloží známá chyba a kontrola ji musí najít.

Hlídá, aby se úpravami kontrol nezhoršil záchyt (benchmark vkládáním chyb, zmenšený pro CI).
"""

import copy
import math
import random
import zlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import substring

from kontrola.config import Config
from kontrola.io.dgn_v8 import read_dgn
from kontrola.io.dxf_loader import load_drawing
from kontrola.model import GeomType
from kontrola.rules import RuleSet
from kontrola.runner import run_checks

ROOT = Path(__file__).resolve().parents[1] / "podklady"
VYKRESY = [
    (ROOT / "zadani1-microstation" / "Vcelak_13_navic.dxf", ROOT / "zadani1-microstation" / "pravidla_zadani1.yaml"),
    (ROOT / "zadani2-husovice" / "Husovice_Včelák_mapa.dgn", ROOT / "zadani2-husovice" / "pravidla_zadani2.yaml"),
]
OPAKOVANI = 3


class Lab:
    def __init__(self, path: Path, yaml: Path):
        self.base = read_dgn(path) if path.suffix == ".dgn" else load_drawing(path)
        self.rs, self.cfg = RuleSet.load(yaml), Config.load(yaml)
        self.cfg.settings("spicka").zapnuto = True
        self.base_keys = {self.key(i) for i in self.run(self.base)}
        rs = self.rs
        self.lines = [f for f in self.base.features if f.geom_type == GeomType.LINIE
                      and f.dxftype in ("LINE", "LWPOLYLINE") and f.geometry.length > 2 and rs.allowed_layer(f.layer)
                      and (rs.resolve(f) is None or rs.resolve(f).topologie)]
        self.geoms = [f.geometry for f in self.base.features if f.geom_type in (GeomType.LINIE, GeomType.POLYGON)]
        self.tree = shapely.STRtree(np.array(self.geoms, dtype=object))

    def run(self, d):
        return run_checks(d, self.rs, self.cfg).issues

    @staticmethod
    def key(i):
        return (i.check_id, round(i.x, 2), round(i.y, 2), i.message)

    def clone(self):
        d = copy.copy(self.base)
        d.features = list(self.base.features)
        return d

    def connected_end(self, f):
        c = list(f.geometry.coords)
        for idx in (0, -1):
            hits = [self.geoms[j] for j in self.tree.query(Point(c[idx]), predicate="dwithin", distance=1e-6)
                    if self.geoms[j] is not f.geometry]
            if hits:
                return idx, hits[0]
        return None


def _move_end(f, idx, dist):
    c = [tuple(p[:2]) for p in f.geometry.coords]
    a, b = (c[0], c[1]) if idx == 0 else (c[-1], c[-2])
    L = math.dist(a, b)
    na = (a[0] + (a[0] - b[0]) / L * dist, a[1] + (a[1] - b[1]) / L * dist)
    c[0 if idx == 0 else -1] = na
    return LineString(c), na


def _set(d, f, **kw):
    nf = replace(f, **kw)
    d.features[d.features.index(f)] = nf
    return nf


def inj_nedotazeni(lab, d, rng):
    for f in rng.sample(lab.lines, len(lab.lines)):
        ce = lab.connected_end(f)
        if ce:
            g, p = _move_end(f, ce[0], -0.005)
            _set(d, f, geometry=g, vertices=list(g.coords))
            return p


def inj_volny_konec(lab, d, rng):
    for f in rng.sample(lab.lines, len(lab.lines)):
        ce = lab.connected_end(f)
        if ce:
            g, p = _move_end(f, ce[0], -0.4)
            _set(d, f, geometry=g, vertices=list(g.coords))
            return p


def inj_duplicita(lab, d, rng):
    f = rng.choice(lab.lines)
    d.features.append(replace(f, fid=10 ** 7, handle="DUP"))
    return f.geometry.interpolate(0.5, normalized=True).coords[0]


def inj_krizeni(lab, d, rng):
    f = rng.choice(lab.lines)
    m = f.geometry.interpolate(0.5, normalized=True)
    q = f.geometry.interpolate(f.geometry.project(m) + 0.05)
    dx, dy = q.x - m.x, q.y - m.y
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return None
    g = LineString([(m.x + dy / L, m.y - dx / L), (m.x - dy / L, m.y + dx / L)])
    d.features.append(replace(f, fid=10 ** 7, handle="X", geometry=g, vertices=list(g.coords), dxftype="LINE"))
    return (m.x, m.y)


def inj_prekryv(lab, d, rng):
    f = rng.choice(lab.lines)
    g = substring(f.geometry, 0.3, 0.7, normalized=True)
    d.features.append(replace(f, fid=10 ** 7, handle="P", geometry=g, vertices=[c[:2] for c in g.coords]))
    return g.interpolate(0.5, normalized=True).coords[0]


def inj_barva(lab, d, rng):
    f = rng.choice(lab.lines)
    attrs = dict(f.attributes)
    attrs["MS_BARVA"] = str((int(attrs.get("MS_BARVA", "0") or 0) + 3) % 16)
    nf = _set(d, f, attributes=attrs, color_rgb=(255, 0, 255), color_aci=6)
    return nf.geometry.interpolate(0.5, normalized=True).coords[0]


def inj_spicka(lab, d, rng):
    f = rng.choice(lab.lines)
    m = f.geometry.interpolate(0.5, normalized=True)
    x, y = m.x + 7, m.y - 7
    g = LineString([(x, y), (x + 3, y), (x + 0.5, y + 0.1)])
    d.features.append(replace(f, fid=10 ** 7, handle="S", geometry=g, vertices=list(g.coords), dxftype="LWPOLYLINE"))
    return (x + 3, y)


def inj_cislo_prepsane(lab, d, rng):
    import re
    t = [f for f in lab.base.features if f.geom_type == GeomType.TEXT and f.text
         and re.fullmatch(r"\d{1,5}", f.text.strip())]
    f, g = rng.sample(t, 2)
    if f.text.strip() == g.text.strip():
        return None
    _set(d, f, text=g.text)
    return (g.geometry.x, g.geometry.y)


def inj_popis_na_popis(lab, d, rng):
    from shapely import affinity

    from kontrola.checks.kartografie import text_box
    t = [f for f in lab.base.features if f.geom_type == GeomType.TEXT and (f.text or "").strip()
         and f.dxftype in ("TEXT", "MTEXT")]
    f, g = rng.sample(t, 2)
    fr = replace(f, rotation=g.rotation)
    bf, bg = text_box(fr), text_box(g)
    if bf is None or bg is None:
        return None
    _set(d, f, rotation=g.rotation, geometry=affinity.translate(f.geometry, bg.centroid.x - bf.centroid.x,
                                                                  bg.centroid.y - bf.centroid.y))
    return (bg.centroid.x, bg.centroid.y)


PRIPADY = {
    "nedotažení 5 mm": (inj_nedotazeni, {"chybejici_napojeni"}),
    "volný konec 40 cm": (inj_volny_konec, {"visici_konce"}),
    "duplicita": (inj_duplicita, {"duplicity"}),
    "křížení bez uzlu": (inj_krizeni, {"pruseciky_bez_uzlu"}),
    "překryv úseku": (inj_prekryv, {"prekryv_linii"}),
    "špatná barva": (inj_barva, {"symbologie", "jednotnost_hladiny"}),
    "špička": (inj_spicka, {"spicka"}),
    "přepsané číslo bodu": (inj_cislo_prepsane, {"duplicitni_cislo_bodu"}),
    "popis na popisu": (inj_popis_na_popis, {"popisy_pres_sebe"}),
}


@pytest.fixture(scope="module", params=VYKRESY, ids=lambda v: v[0].stem)
def lab(request):
    path, yaml = request.param
    if not path.exists():
        pytest.skip("výkres ze zadání chybí")
    return Lab(path, yaml)


@pytest.mark.parametrize("nazev", list(PRIPADY))
def test_vlozena_chyba_se_najde(lab, nazev):
    fn, expect = PRIPADY[nazev]
    rng = random.Random(zlib.crc32(nazev.encode()))
    tried = 0
    for _ in range(OPAKOVANI * 3):
        if tried == OPAKOVANI:
            break
        d = lab.clone()
        p = fn(lab, d, rng)
        if p is None:
            continue
        tried += 1
        new = [i for i in lab.run(d) if lab.key(i) not in lab.base_keys]
        hit = [i for i in new if i.check_id in expect and math.dist((i.x, i.y), p[:2]) < 1.0]
        assert hit, f"{nazev} v {p} nenalezeno; nově hlášeno: {[(i.check_id, i.message) for i in new][:5]}"
    assert tried, "nepodařilo se vložit chybu"
