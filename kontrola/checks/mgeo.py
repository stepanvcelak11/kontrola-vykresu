"""Kontroly podle MGEO (GISoft), které doplňují kontrolu čárové kresby.

* **Prvky příliš blízko (Limit)** – MGEO při topologickém čištění hlídá, aby vzdálenost dvou prvků
  neklesla pod zadaný Limit, pokud se nedotýkají: lomový bod čáry těsně vedle jiné čáry je chyba
  (čáry se mají buď dotýkat, nebo být dál od sebe).
* **Kontrola ploch** – z hraničních čar se sestaví plochy a hlídá se, že každá má právě jeden popis
  / definiční bod (číslo parcely, značku druhu pozemku), chybějící, vícenásobné a duplicitní popisy.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np
import shapely

from ..model import GeomType
from ..rules import layer_matches
from .base import Check, CheckContext, Param, Severity, fmt_m, fmt_num, register


@register
class BlizkePrvky(Check):
    id = "blizke_prvky"
    nazev = "Prvky příliš blízko (Limit)"
    skupina = "Topologie"
    popis = ("Lomový bod čáry leží těsně u jiné čáry, ale nedotýká se jí (MGEO: vzdálenost prvků pod Limitem). "
             "Čáry se mají buď přesně dotýkat, nebo být od sebe dál. Konce čar řeší kontrola nedotažení.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [Param("limit", "Limit [m]", "float", 0.01,
                       "Vzdálenost, pod kterou se dva nedotýkající se prvky považují za chybu (MGEO Limit).")]

    def run(self, ctx: CheckContext):
        limit = float(ctx.param("limit", 0.01))
        eps = max(ctx.precision, 1e-6)
        feats = ctx.linear()
        if len(feats) < 2 or limit <= eps:
            return
        geoms = np.array([ctx.boundary(f) for f in feats], dtype=object)
        tree = shapely.STRtree(geoms)
        pts, owner = [], []
        for i, f in enumerate(feats):
            v = f.vertices
            inner = v[1:-1] if f.geom_type == GeomType.LINIE else v  # konce čar řeší jiná kontrola
            for p in inner:
                pts.append(p[:2])
                owner.append(i)
        if not pts:
            return
        pg = shapely.points(np.asarray(pts, dtype=float))
        pi, gi = tree.query(pg, predicate="dwithin", distance=limit)
        owner = np.asarray(owner)
        m = gi != owner[pi]
        pi, gi = pi[m], gi[m]
        if not len(pi):
            return
        d = shapely.distance(pg[pi], geoms[gi])
        sel = d > eps
        seen = set()
        for a, b, dist in zip(pi[sel], gi[sel], d[sel]):
            x, y = pts[a]
            key = (round(x, 3), round(y, 3))
            if key in seen:
                continue
            # dotýká se bod jiné čáry jinde (uzel) → v pořádku
            touching = [k for k in tree.query(pg[a], predicate="dwithin", distance=eps) if k != owner[a]]
            if touching:
                continue
            seen.add(key)
            yield ctx.issue(self, [feats[owner[a]], feats[b]],
                            f"Lomový bod je {fmt_m(float(dist))} od jiné čáry, ale nedotýká se jí", at=(x, y))


def _auto_layers(ctx: CheckContext, words: tuple[str, ...], exclude: tuple[str, ...] = ()) -> list[str]:
    import unicodedata
    out = []
    for name, li in ctx.drawing.layers.items():
        n = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
        if li.count and any(w in n for w in words) and not any(w in n for w in exclude):
            out.append(name)
    return out


@register
class KontrolaPloch(Check):
    id = "kontrola_ploch"
    nazev = "Kontrola ploch (popis v ploše)"
    skupina = "Topologie"
    popis = ("Jako „Kontrola ploch“ v MGEO: z hraničních čar sestaví plochy a hlídá, že každá plocha má popis "
             "nebo definiční bod (číslo parcely, značku druhu pozemku) – chybějící, více popisů v jedné ploše a "
             "stejné číslo ve dvou plochách. Vrstvy se poznají samy (hranice, popis ploch), nebo je zadejte.")
    vychozi_zavaznost = Severity.VAROVANI
    vychozi_zapnuto = False
    parametry = [
        Param("vrstvy_hranic", "Vrstvy hranic ploch (čárkou, * = zástupný znak)", "layers", "",
              "Prázdné = vrstvy, jejichž název obsahuje „hranic“ nebo „parcel“."),
        Param("vrstvy_popisu", "Vrstvy popisů / definičních bodů", "layers", "",
              "Prázdné = vrstvy s „popis“ a „ploch“ / „parc“ / „druh“ v názvu a buňky ploch."),
        Param("min_plocha", "Hlásit plochy větší než [m²]", "float", 2.0),
    ]

    def run(self, ctx: CheckContext):
        def layers(param, words, exclude=()):
            v = ctx.param(param, "")
            if isinstance(v, str):
                v = [s.strip() for s in v.split(",") if s.strip()]
            return list(v or []) or _auto_layers(ctx, words, exclude)
        hr = layers("vrstvy_hranic", ("hranic", "parcel", "rozhr"), ("cisl", "popis", "bunk"))
        pop = layers("vrstvy_popisu", ("popis-ploch", "plochy-bunk", "cisla parcel", "druh", "parcelni"))
        if not hr or not pop:
            ctx.notes.append("kontrola ploch: nenašly se vrstvy hranic nebo popisů ploch – zadejte je v Nastavení.")
            return
        min_area = float(ctx.param("min_plocha", 2.0))
        lines = [ctx.boundary(f) for f in ctx.features()
                 if f.geom_type in (GeomType.LINIE, GeomType.POLYGON) and any(layer_matches(h, f.layer) for h in hr)]
        if not lines:
            return
        try:
            noded = shapely.get_parts(shapely.union_all(np.array(lines, dtype=object)))
            faces = list(shapely.get_parts(shapely.polygonize(noded)))
        except shapely.errors.GEOSException:
            ctx.notes.append("kontrola ploch: hranice nejde sestavit do ploch (chyby topologie – opravte je nejdřív).")
            return
        faces = [p for p in faces if p.area >= min_area]
        labels = [f for f in ctx.features()
                  if f.geom_type in (GeomType.TEXT, GeomType.BOD) and any(layer_matches(h, f.layer) for h in pop)]
        if not faces:
            ctx.notes.append("kontrola ploch: z hranic nevznikla žádná uzavřená plocha.")
            return
        tree = shapely.STRtree(np.array(faces, dtype=object))
        inside: dict[int, list] = defaultdict(list)
        for lab in labels:
            g = lab.geometry if lab.geometry.geom_type == "Point" else lab.geometry.representative_point()
            for k in tree.query(g, predicate="within"):
                inside[int(k)].append(lab)
        texts_where: dict[str, set[int]] = defaultdict(set)
        for k, face in enumerate(faces):
            labs = inside.get(k, [])
            c = face.representative_point()
            if not labs:
                yield ctx.issue(self, None, f"Plocha {fmt_num(face.area, 1)} m² nemá popis ani definiční bod",
                                at=(c.x, c.y), geometry=face)
                continue
            texts = [lab for lab in labs if lab.geom_type == GeomType.TEXT and lab.text]
            per_layer = Counter(lab.layer for lab in texts)
            for layer, n in per_layer.items():
                if n > 1 and any(w in layer.lower() for w in ("parc", "cisl")):
                    yield ctx.issue(self, [t for t in texts if t.layer == layer],
                                    f"V ploše je {n}× číslo na vrstvě {layer}", at=(c.x, c.y), geometry=face)
            for t in texts:
                if any(w in t.layer.lower() for w in ("parc", "cisl")):
                    texts_where[t.text.strip()].add(k)
        for txt, where in texts_where.items():
            if len(where) > 1:
                c = faces[min(where)].representative_point()
                yield ctx.issue(self, None, f"Číslo „{txt}“ je ve {len(where)} plochách (duplicita)", at=(c.x, c.y))
        ctx.notes.append(f"kontrola ploch: {len(faces)} ploch z vrstev {', '.join(hr[:3])}"
                         f"{'…' if len(hr) > 3 else ''}.")


