"""Mračna bodů (laserové skenování, fotogrammetrie, DMR 5G): načtení XYZ / LAS / PLY, prořídnutí do mřížky
a výběr bodů terénu – vstup pro TIN, vrstevnice a profil (``geodezie.teren``).

Souřadnice: S-JTSK kladné (Y, X) i záporné (EPSG:5514 jako ve výkresech MicroStationu) – ``do_vykresu``
vrátí body ve výkresových souřadnicích (x = −Y, y = −X). LAZ (komprimovaný LAS) se nečte – převeďte ho na LAS
(např. LAStools, CloudCompare). Bez Qt; potřebuje jen numpy.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TERÉN_LAS = 2  # třída „terén“ (ground) v LAS


@dataclass
class Mracno:
    body: np.ndarray  # N×3 (první dvě souřadnice, výška)
    trida: np.ndarray | None = None  # klasifikace LAS (2 = terén), jinak None
    zdroj: str = ""

    def __len__(self) -> int:
        return len(self.body)

    def rozsah(self) -> tuple[float, float, float, float, float, float]:
        mn, mx = self.body.min(axis=0), self.body.max(axis=0)
        return float(mn[0]), float(mn[1]), float(mn[2]), float(mx[0]), float(mx[1]), float(mx[2])

    def do_vykresu(self) -> np.ndarray:
        """Body ve výkresových souřadnicích (x = −Y, y = −X). Kladné S-JTSK (Y < X) se převrátí,
        záporné (EPSG:5514) a místní souřadnice zůstanou."""
        b = self.body.copy()
        a, c = np.median(b[:, 0]), np.median(b[:, 1])
        if a > 0 and c > 0 and 200_000 < a < 1_000_000 and 900_000 < c < 1_400_000:  # S-JTSK kladné Y, X
            b[:, 0], b[:, 1] = -self.body[:, 0], -self.body[:, 1]
        return b


# ------------------------------------------------------------------ načtení
def nacti(cesta: str | Path, max_bodu: int = 20_000_000) -> Mracno:
    p = Path(cesta)
    s = p.suffix.lower()
    if s == ".laz":
        raise ValueError("Komprimovaný LAZ neumím číst – převeďte ho na LAS (CloudCompare, LAStools las2las).")
    with open(p, "rb") as f:
        zacatek = f.read(4)
    if zacatek == b"LASF":
        return _las(p, max_bodu)
    if zacatek[:3] == b"ply":
        return _ply(p, max_bodu)
    return _xyz(p, max_bodu)


def _xyz(p: Path, max_bodu: int) -> Mracno:
    """Textové mračno: řádky „x y z …“ (nebo „číslo Y X Z“), oddělovač mezera, čárka, středník, tabulátor."""
    out = []
    cislo = re.compile(r"^[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?$")
    with open(p, encoding="utf-8", errors="replace") as f:
        for radek in f:
            casti = [c for c in re.split(r"[\s;]+" if ";" in radek or "\t" in radek or " " in radek else r",", radek.strip()) if c]
            cisla = [c for c in casti if cislo.match(c)]
            if len(casti) >= 4 and not cislo.match(casti[0]):  # „číslo Y X Z“ s textovým číslem bodu
                cisla = [c for c in casti[1:] if cislo.match(c)]
            elif len(cisla) >= 4 and len(casti) >= 4 and "." not in casti[0] and "," not in casti[0]:
                cisla = cisla[1:]  # celé číslo bodu na začátku
            if len(cisla) < 3:
                continue
            out.append([float(c.replace(",", ".")) for c in cisla[:3]])
            if len(out) >= max_bodu:
                break
    if not out:
        raise ValueError(f"{p.name}: nenašel jsem žádné body „x y z“.")
    return Mracno(np.array(out, dtype=float), None, p.name)


def _las(p: Path, max_bodu: int) -> Mracno:
    data = p.read_bytes()
    if len(data) < 227:
        raise ValueError(f"{p.name}: poškozená hlavička LAS.")
    verze = (data[24], data[25])
    offset = struct.unpack_from("<I", data, 96)[0]
    fmt = data[104] & 0x3F
    delka = struct.unpack_from("<H", data, 105)[0]
    n = struct.unpack_from("<I", data, 107)[0]
    if n == 0 and verze >= (1, 4) and len(data) >= 255:
        n = struct.unpack_from("<Q", data, 247)[0]
    sx, sy, sz = struct.unpack_from("<3d", data, 131)
    ox, oy, oz = struct.unpack_from("<3d", data, 155)
    n = min(n, (len(data) - offset) // delka, max_bodu)
    if n <= 0:
        raise ValueError(f"{p.name}: LAS neobsahuje žádné body.")
    zaznamy = np.frombuffer(data, dtype=np.uint8, count=n * delka, offset=offset).reshape(n, delka)
    xyz = zaznamy[:, :12].copy().view("<i4").reshape(n, 3).astype(float)
    body = np.column_stack([xyz[:, 0] * sx + ox, xyz[:, 1] * sy + oy, xyz[:, 2] * sz + oz])
    trida = (zaznamy[:, 16] if fmt >= 6 else zaznamy[:, 15] & 0x1F).astype(np.uint8)
    return Mracno(body, trida, p.name)


_PLY_TYPY = {"char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1", "short": "i2", "int16": "i2",
             "ushort": "u2", "uint16": "u2", "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
             "float": "f4", "float32": "f4", "double": "f8", "float64": "f8"}


def _ply(p: Path, max_bodu: int) -> Mracno:
    data = p.read_bytes()
    konec = data.find(b"end_header")
    if konec < 0:
        raise ValueError(f"{p.name}: chybí hlavička PLY.")
    hlava = data[:konec].decode("ascii", errors="replace").splitlines()
    telo = data[data.index(b"\n", konec) + 1:]
    fmt, n, vlastnosti, ve_vertex = "ascii", 0, [], False
    for r in hlava:
        t = r.split()
        if not t:
            continue
        if t[0] == "format":
            fmt = t[1]
        elif t[0] == "element":
            ve_vertex = t[1] == "vertex"
            if ve_vertex:
                n = int(t[2])
        elif t[0] == "property" and ve_vertex:
            if t[1] == "list":
                raise ValueError(f"{p.name}: seznamové vlastnosti bodů PLY nejsou podporované.")
            vlastnosti.append((t[2], _PLY_TYPY.get(t[1], "f4")))
    jmena = [v[0] for v in vlastnosti]
    if not {"x", "y", "z"} <= set(jmena):
        raise ValueError(f"{p.name}: body PLY nemají x, y, z.")
    n = min(n, max_bodu)
    if fmt == "ascii":
        radky = telo.decode("ascii", errors="replace").split("\n")[:n]
        pole = np.array([[float(c) for c in r.split()[:len(jmena)]] for r in radky if r.strip()], dtype=float)
        body = pole[:, [jmena.index("x"), jmena.index("y"), jmena.index("z")]]
    else:
        endian = "<" if "little" in fmt else ">"
        dt = np.dtype([(j, endian + t) for j, t in vlastnosti])
        pole = np.frombuffer(telo, dtype=dt, count=n)
        body = np.column_stack([pole["x"].astype(float), pole["y"].astype(float), pole["z"].astype(float)])
    return Mracno(body, None, p.name)


# ------------------------------------------------------------------ zpracování
def prorid(m: Mracno, bunka: float = 1.0, rezim: str = "teren") -> Mracno:
    """Prořídnutí do mřížky ``bunka`` m: v každé buňce jeden bod – nejnižší („teren“, odstraní vegetaci
    a stavby nad terénem), nejvyšší („povrch“) nebo nejbližší ke středu buňky („stred“)."""
    if bunka <= 0:
        raise ValueError("Velikost buňky musí být kladná.")
    b = m.body
    if not len(b):
        return m
    ix = np.floor((b[:, 0] - b[:, 0].min()) / bunka).astype(np.int64)
    iy = np.floor((b[:, 1] - b[:, 1].min()) / bunka).astype(np.int64)
    klic = ix * (int(iy.max()) + 1) + iy
    if rezim == "teren":
        kriterium = b[:, 2]
    elif rezim == "povrch":
        kriterium = -b[:, 2]
    else:
        cx = b[:, 0].min() + (ix + 0.5) * bunka
        cy = b[:, 1].min() + (iy + 0.5) * bunka
        kriterium = (b[:, 0] - cx) ** 2 + (b[:, 1] - cy) ** 2
    poradi = np.lexsort((kriterium, klic))
    prvni = np.ones(len(poradi), dtype=bool)
    prvni[1:] = klic[poradi][1:] != klic[poradi][:-1]
    vyber = poradi[prvni]
    return Mracno(b[vyber], None if m.trida is None else m.trida[vyber], m.zdroj)


def teren(m: Mracno, bunka: float = 1.0, max_nad: float = 0.5) -> Mracno:
    """Body terénu: má-li LAS klasifikaci terénu (třída 2), použije se; jinak nejnižší body v mřížce a vyřazení
    bodů, které jsou o víc než ``max_nad`` m nad mediánem okolních buněk (keře, auta, zídky)."""
    if m.trida is not None and np.any(m.trida == TERÉN_LAS):
        sel = m.trida == TERÉN_LAS
        return prorid(Mracno(m.body[sel], m.trida[sel], m.zdroj), bunka, "teren")
    r = prorid(m, bunka, "teren")
    b = r.body
    if len(b) < 9:
        return r
    ix = np.floor((b[:, 0] - b[:, 0].min()) / bunka).astype(np.int64)
    iy = np.floor((b[:, 1] - b[:, 1].min()) / bunka).astype(np.int64)
    mrizka = {}
    for i, (a, c) in enumerate(zip(ix, iy)):
        mrizka[(a, c)] = b[i, 2]
    ponechat = np.ones(len(b), dtype=bool)
    for i, (a, c) in enumerate(zip(ix, iy)):
        okoli = [mrizka[k] for k in ((a + dx, c + dy) for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2))
                 if k in mrizka and k != (a, c)]
        if len(okoli) >= 4 and b[i, 2] - float(np.median(okoli)) > max_nad:
            ponechat[i] = False
    return Mracno(b[ponechat], None, m.zdroj)


def souhrn(m: Mracno) -> str:
    x0, y0, z0, x1, y1, z1 = m.rozsah()
    t = f"{len(m):,} bodů".replace(",", " ") + f", rozsah {x1 - x0:.1f} × {y1 - y0:.1f} m, výšky {z0:.2f}–{z1:.2f} m"
    if m.trida is not None:
        t += f", terén (třída 2): {int(np.sum(m.trida == TERÉN_LAS)):,}".replace(",", " ")
    return t
