"""Zápis výkresu do DGN V7 (Intergraph ISFF) – formát, který MicroStation otevře přímo (i V8i/CONNECT,
odkud ho jde uložit jako V8).

Proč V7: formát prvků V7 je veřejně popsaný (ISFF), formát V8 ne. Prvky se zapisují s číslem hladiny
1–63, barvou 0–255 (tabulka barev MicroStationu), tloušťkou wt 0–31 a stylem 0–7 – tedy ve stejných
číslech, jaké kontroluje Směrnice. Úsečky, lomené čáry (do 101 vrcholů, delší se rozdělí), tvary,
kružnice a elipsy, oblouky, texty (i víceřádkové po řádcích), body (úsečka nulové délky) a buňky
(hlavička buňky + prvky, název do 6 znaků jako v MicroStationu V7).

Šablona (seed): prázdný 2D výkres z GDAL (``resources/dgn_seed_2d.dgn``, licence MIT); jednotky se
nastaví na metry / milimetry (1000 UOR na metr) a globální počátek na 0 – S-JTSK se vejde do rozsahu V7.
Lze předat i vlastní šablonu od učitele (např. UGEO.DGN).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "resources" / "dgn_seed_2d.dgn"
UOR = 1000.0  # UOR na metr (1 mm)
MAX_VRCHOLU = 101
_RAD50 = " ABCDEFGHIJKLMNOPQRSTUVWXYZ$.?0123456789"


class ChybaDgn(ValueError):
    pass


# ------------------------------------------------------------------ kódování čísel
def _i32(v: int) -> bytes:
    """32bit celé číslo v pořadí DGN (horní slovo první, slova little-endian)."""
    b = struct.pack("<i", int(v))
    return bytes((b[2], b[3], b[0], b[1]))


def _u32(v: int) -> bytes:
    b = struct.pack("<I", int(v) & 0xFFFFFFFF)
    return bytes((b[2], b[3], b[0], b[1]))


def _i16(v: int) -> bytes:
    return struct.pack("<H", int(v) & 0xFFFF)


def vax_double(x: float) -> bytes:
    """IEEE double → VAX D-float v pořadí bajtů DGN (jako IEEE2DGNDouble v GDAL)."""
    if x == 0 or not math.isfinite(x):
        return bytes(8)
    hi, lo = struct.unpack("<II", struct.pack("<d", x)[4:] + struct.pack("<d", x)[:4])
    sign = hi & 0x80000000
    exp = (hi >> 20) & 0x7FF
    if exp:
        exp = exp - 1023 + 129
    if exp > 255:
        hi, lo = sign | 0x7FFFFFFF, 0xFFFFFFFF
    elif exp <= 0:
        return bytes(8)
    else:  # mantisa IEEE (52 b) → VAX (55 b): posun o 3 bity doleva
        hi, lo = (((hi & 0x000FFFFF) << 3) | (lo >> 29) | (exp << 23) | sign), (lo << 3) & 0xFFFFFFFF
    s = struct.pack("<II", hi, lo)
    return bytes((s[2], s[3], s[0], s[1], s[6], s[7], s[4], s[5]))


def rad50(nazev: str) -> bytes:
    """Název buňky do dvou slov RAD-50 (6 znaků: A–Z, 0–9, tečka, $)."""
    t = "".join(c if c in _RAD50 else "" for c in nazev.upper())[:6].ljust(6)
    out = b""
    for i in (0, 3):
        v = 0
        for c in t[i:i + 3]:
            v = v * 40 + _RAD50.index(c)
        out += _i16(v)
    return out


def _uor(v: float) -> int:
    n = int(round(v * UOR))
    if not -2 ** 31 < n < 2 ** 31:
        raise ChybaDgn("Souřadnice jsou mimo rozsah DGN V7 (±2 147 km) – je výkres v metrech?")
    return n


# ------------------------------------------------------------------ prvky
@dataclass
class Symbologie:
    hladina: int = 1
    barva: int = 0
    tloustka: int = 0
    styl: int = 0

    def slovo(self) -> bytes:
        return _i16((self.styl & 7) | ((self.tloustka & 31) << 3) | ((self.barva & 255) << 8))


@dataclass
class Prvek:
    typ: int
    sym: Symbologie
    data: bytes  # vše za 36bajtovou hlavičkou
    rozsah: tuple[float, float, float, float]  # xmin, ymin, xmax, ymax [m]
    deti: list = field(default_factory=list)  # prvky buňky
    komplexni: bool = False

    def bajty(self) -> bytes:
        telo = self.data
        if len(telo) % 2:
            telo += b"\x00"
        delka = 36 + len(telo)
        hl = bytes((self.sym.hladina & 0x3F | (0x80 if self.komplexni else 0), self.typ & 0x7F))
        hl += _i16(delka // 2 - 2)
        x0, y0, x1, y1 = self.rozsah
        for v in (_uor(x0), _uor(y0), 0, _uor(x1), _uor(y1), 0):
            hl += _u32(v ^ 0x80000000)
        hl += _i16(0)  # grafická skupina
        hl += _i16(delka // 2 - 16)  # slova do připojených dat (žádná nejsou)
        hl += _i16(0)  # vlastnosti
        hl += self.sym.slovo()
        return hl + telo + b"".join(d.bajty() for d in self.deti)

    def velikost(self) -> int:
        return 36 + len(self.data) + len(self.data) % 2 + sum(d.velikost() for d in self.deti)


def _rozsah(body) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in body], [p[1] for p in body]
    return min(xs), min(ys), max(xs), max(ys)


def _body(body) -> bytes:
    return b"".join(_i32(_uor(x)) + _i32(_uor(y)) for x, y in body)


def usecka(a, b, sym: Symbologie) -> Prvek:
    return Prvek(3, sym, _body([a, b]), _rozsah([a, b]))


def lomena(body, sym: Symbologie, uzavrena: bool = False) -> list[Prvek]:
    """Lomená čára (typ 4) nebo tvar (typ 6); přes 101 vrcholů se rozdělí na navazující části."""
    pts = [tuple(p[:2]) for p in body]
    if uzavrena and pts[0] != pts[-1]:
        pts.append(pts[0])
    if len(pts) < 2:
        return []
    if len(pts) == 2 and not uzavrena:
        return [usecka(pts[0], pts[1], sym)]
    if len(pts) <= MAX_VRCHOLU:
        return [Prvek(6 if uzavrena and len(pts) >= 4 else 4, sym, _i16(len(pts)) + _body(pts), _rozsah(pts))]
    out, i = [], 0
    while i < len(pts) - 1:
        cast = pts[i:i + MAX_VRCHOLU]
        out.append(Prvek(4, sym, _i16(len(cast)) + _body(cast), _rozsah(cast)))
        i += MAX_VRCHOLU - 1
    return out


def elipsa(stred, a: float, b: float, natoceni_deg: float, sym: Symbologie) -> Prvek:
    data = (vax_double(a * UOR) + vax_double(b * UOR) + _i32(round(natoceni_deg * 360000))
            + vax_double(stred[0] * UOR) + vax_double(stred[1] * UOR))
    r = max(a, b)
    return Prvek(15, sym, data, (stred[0] - r, stred[1] - r, stred[0] + r, stred[1] + r))


def oblouk(stred, r: float, zacatek_deg: float, rozsah_deg: float, sym: Symbologie) -> Prvek:
    """Kruhový oblouk proti směru hodinových ručiček od úhlu ``zacatek_deg`` o ``rozsah_deg``."""
    sweep = int(round(abs(rozsah_deg) * 360000))
    if rozsah_deg < 0:
        sweep |= 0x80000000
    data = (_i32(round(zacatek_deg * 360000)) + _u32(sweep) + vax_double(r * UOR) + vax_double(r * UOR)
            + _i32(0) + vax_double(stred[0] * UOR) + vax_double(stred[1] * UOR))
    # rozsah: krajní body oblouku a kvadranty, které oblouk obsahuje
    body = []
    k = zacatek_deg
    for i in range(0, 361, 5):
        u = k + rozsah_deg * i / 360
        body.append((stred[0] + r * math.cos(math.radians(u)), stred[1] + r * math.sin(math.radians(u))))
    return Prvek(16, sym, data, _rozsah(body))


# zarovnání textu DGN: vlevo 0–2, na střed 6–8, vpravo 12–14 (nahoře / uprostřed / dole)
def zarovnani(h: int, v: int) -> int:
    """``h`` 0 vlevo, 1 střed, 2 vpravo; ``v`` 0 účaří, 1 dole, 2 uprostřed, 3 nahoře (jako DXF)."""
    radek = {3: 0, 2: 1, 1: 2, 0: 2}.get(v, 2)
    return {0: 0, 1: 6, 2: 12}.get(h, 0) + radek


def text(bod, retezec: str, vyska: float, sym: Symbologie, natoceni_deg: float = 0.0, font: int = 1,
         just: int = 2, sirka: float | None = None) -> Prvek:
    """Text (typ 17). Délka/výška písma v UOR × 1000/6 jako v MicroStationu."""
    raw = retezec.encode("cp1250", errors="replace")[:255]
    s = sirka if sirka else vyska
    data = (bytes((font & 0xFF, just & 0xFF)) + _i32(round(s * UOR * 1000 / 6)) + _i32(round(vyska * UOR * 1000 / 6))
            + _i32(round(natoceni_deg * 360000)) + _i32(_uor(bod[0])) + _i32(_uor(bod[1]))
            + bytes((len(raw), 0)) + raw)
    # přibližný rozsah: řádek textu od počátku ve směru natočení
    delka = max(s, 1e-6) * max(1, len(retezec))
    c, si = math.cos(math.radians(natoceni_deg)), math.sin(math.radians(natoceni_deg))
    rohy = [(0, 0), (delka, 0), (delka, vyska), (0, vyska)]
    dx = {0: 0.0, 6: -delka / 2, 12: -delka}.get(just - just % 6 if just < 15 else 0, 0.0)
    dy = {0: -vyska, 1: -vyska / 2, 2: 0.0}.get(just % 6, 0.0)
    body = [(bod[0] + (x + dx) * c - (y + dy) * si, bod[1] + (x + dx) * si + (y + dy) * c) for x, y in rohy]
    return Prvek(17, sym, data, _rozsah(body))


def bunka(nazev: str, pocatek, natoceni_deg: float, deti: list[Prvek], sym: Symbologie) -> Prvek:
    """Hlavička buňky (typ 2) s prvky v souřadnicích výkresu."""
    if not deti:
        raise ChybaDgn(f"Buňka {nazev} nemá žádné prvky.")
    for d in deti:
        d.komplexni = True
    x0 = min(d.rozsah[0] for d in deti)
    y0 = min(d.rozsah[1] for d in deti)
    x1 = max(d.rozsah[2] for d in deti)
    y1 = max(d.rozsah[3] for d in deti)
    hladiny = 0
    for d in deti:
        hladiny |= 1 << (max(1, min(63, d.sym.hladina)) - 1)
    c, s = math.cos(math.radians(natoceni_deg)), math.sin(math.radians(natoceni_deg))
    m = [c, -s, s, c]
    data = _i16(0)  # počet slov popisu – doplní se níž
    data += rad50(nazev) + _i16(0)
    data += b"".join(_i16((hladiny >> (16 * i)) & 0xFFFF) for i in range(4))
    data += b"".join(_i32(_uor(v)) for v in (x0, y0, x1, y1))
    data += b"".join(_i32(max(-2 ** 31 + 1, min(2 ** 31 - 1, round(v * 2 ** 31)))) for v in m)
    data += _i32(_uor(pocatek[0])) + _i32(_uor(pocatek[1]))
    p = Prvek(2, sym, data, (x0, y0, x1, y1), deti)
    slov = p.velikost() // 2 - 19
    if slov > 0xFFFF:
        raise ChybaDgn(f"Buňka {nazev} je pro DGN V7 příliš velká.")
    p.data = _i16(slov) + data[2:]
    return p


# ------------------------------------------------------------------ soubor
def _seed(seed: Path | None) -> bytes:
    d = bytearray(Path(seed or SEED).read_bytes())
    if len(d) < 1536 or d[1] & 0x7F != 9:
        raise ChybaDgn("Šablona není výkres DGN V7.")
    if d[1214] & 0x40:
        raise ChybaDgn("Šablona je 3D – použijte 2D šablonu.")
    # jednotky: hlavní m, vedlejší mm, 1000 UOR na metr; globální počátek 0
    d[1112:1116] = _i32(1000)
    d[1116:1120] = _i32(1)
    d[1120:1124] = b"m\x00mm"
    d[1240:1264] = bytes(24)
    off = 0
    while off + 4 <= len(d) and d[off:off + 2] != b"\xff\xff":
        off += 4 + 2 * struct.unpack_from("<H", d, off + 2)[0]
    return bytes(d[:off])


def zapis(prvky: list[Prvek], cesta: str | Path, seed: str | Path | None = None) -> Path:
    data = _seed(Path(seed) if seed else None) + b"".join(p.bajty() for p in prvky) + b"\xff\xff"
    if len(data) % 512:  # MicroStation zarovnává soubor na bloky 512 B
        data += bytes(512 - len(data) % 512)
    import os
    import tempfile
    p = Path(cesta)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return p
