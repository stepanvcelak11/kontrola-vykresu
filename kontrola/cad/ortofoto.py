"""Ortofoto ČÚZK jako podklad výkresu: stažení výřezu z veřejné WMS služby v S-JTSK (EPSG:5514).

Souřadnice výkresu z MicroStationu (x = −Y, y = −X) jsou přímo souřadnice EPSG:5514, takže výřez pohledu
jde rovnou do dotazu GetMap. Obrázek se uloží jako JPG s world filem (.jgw) – připojí se jako běžný rastr
(DXF IMAGE) a otevře ho i MicroStation, AutoCAD nebo QGIS. Stejný výřez se podruhé nestahuje.
"""

from __future__ import annotations

import math
import urllib.parse
import urllib.request
from pathlib import Path

WMS_ORTOFOTO = "https://ags.cuzk.gov.cz/arcgis1/services/ORTOFOTO/MapServer/WMSServer"
MAX_PX = 4000  # nejdelší strana obrázku (limit služby ČÚZK)
MIN_PIXEL = 0.1  # m – jemněji ortofoto stejně není (rozlišení cca 0,125–0,25 m)


class ChybaOrtofota(Exception):
    pass


def rozmery(sirka_m: float, vyska_m: float, max_px: int = MAX_PX) -> tuple[int, int, float]:
    """Počet pixelů (šířka, výška) a velikost pixelu [m] pro výřez – co nejjemněji, ale nejvýš max_px."""
    if sirka_m <= 0 or vyska_m <= 0:
        raise ChybaOrtofota("Výřez nemá žádnou plochu.")
    pixel = max(MIN_PIXEL, max(sirka_m, vyska_m) / max_px)
    return max(1, round(sirka_m / pixel)), max(1, round(vyska_m / pixel)), pixel


def je_sjtsk(x: float, y: float) -> bool:
    """Výkres v S-JTSK se zápornými souřadnicemi (Česko: Y 430–905 km, X 935–1 230 km)."""
    return -910_000 < x < -420_000 and -1_240_000 < y < -930_000


def url(bbox: tuple[float, float, float, float], w: int, h: int, sluzba: str = WMS_ORTOFOTO) -> str:
    """GetMap ve verzi 1.1.1 – pořadí os v BBOX je vždy x, y (u 1.3.0 by záviselo na definici EPSG)."""
    q = {"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "LAYERS": "0", "STYLES": "",
         "SRS": "EPSG:5514", "BBOX": ",".join(f"{v:.2f}" for v in bbox), "WIDTH": str(w), "HEIGHT": str(h),
         "FORMAT": "image/jpeg"}
    return sluzba + "?" + urllib.parse.urlencode(q)


def world_file_text(bbox, w: int, h: int) -> str:
    """World file: velikost pixelu, natočení 0, střed levého horního pixelu."""
    px = (bbox[2] - bbox[0]) / w
    py = (bbox[3] - bbox[1]) / h
    return "\n".join(f"{v:.6f}" for v in (px, 0.0, 0.0, -py, bbox[0] + px / 2, bbox[3] - py / 2)) + "\n"


def stahni(bbox: tuple[float, float, float, float], slozka: str | Path, max_px: int = MAX_PX,
           otevri=None, timeout: float = 60.0) -> Path:
    """Stáhne ortofoto výřezu do složky (JPG + JGW) a vrátí cestu k obrázku. ``otevri`` jde podstrčit v testech."""
    x0, y0, x1, y1 = bbox
    if not (je_sjtsk(x0, y0) and je_sjtsk(x1, y1)):
        raise ChybaOrtofota("Výkres není v S-JTSK (souřadnice −Y, −X jako z MicroStationu) – ortofoto ČÚZK "
                            "nejde umístit. Přibližte výřez na kresbu v S-JTSK.")
    w, h, pixel = rozmery(x1 - x0, y1 - y0, max_px)
    # výřez zarovnaný na celé pixely – obrázek sedí přesně na souřadnice
    x1, y1 = x0 + w * pixel, y0 + h * pixel
    bbox = (x0, y0, x1, y1)
    slozka = Path(slozka)
    slozka.mkdir(parents=True, exist_ok=True)
    jmeno = f"ortofoto_{-x0:.0f}_{-y0:.0f}_{-x1:.0f}_{-y1:.0f}_{pixel * 100:.0f}cm"
    cil = slozka / (jmeno + ".jpg")
    if cil.exists() and cil.stat().st_size > 0 and cil.with_suffix(".jgw").exists():
        return cil
    otevri = otevri or (lambda u: urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": "KontrolaVykresu"}), timeout=timeout))
    try:
        with otevri(url(bbox, w, h)) as odp:
            typ = (odp.headers.get("Content-Type") or "") if getattr(odp, "headers", None) else ""
            data = odp.read()
    except OSError as e:
        raise ChybaOrtofota(f"Ortofoto se nepodařilo stáhnout (ČÚZK): {e}") from e
    if not data or ("xml" in typ.lower() or data[:1] == b"<"):
        zprava = data[:300].decode("utf-8", "replace") if data else "prázdná odpověď"
        raise ChybaOrtofota(f"Služba ČÚZK nevrátila obrázek: {zprava}")
    tmp = cil.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(cil)
    cil.with_suffix(".jgw").write_text(world_file_text(bbox, w, h), encoding="ascii")
    return cil


def popis_rozliseni(pixel: float) -> str:
    return f"{pixel * 100:.0f} cm/px" if pixel < 1 else f"{pixel:.1f} m/px"


def zaokrouhli_vyrez(x0, y0, x1, y1, krok: float = 1.0):
    """Výřez na celé metry (stejný výřez → stejný soubor v mezipaměti)."""
    return (math.floor(x0 / krok) * krok, math.floor(y0 / krok) * krok,
            math.ceil(x1 / krok) * krok, math.ceil(y1 / krok) * krok)
