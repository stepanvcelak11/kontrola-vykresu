"""Převod S-JTSK (Křovákovo zobrazení, Besselův elipsoid) ↔ WGS84 / ETRS89 (zeměpisné souřadnice).

Vlastní implementace podle vzorců Křovákova zobrazení (EPSG metoda 9819) a sedmiprvkové Helmertovy
transformace. Parametry transformace: S-JTSK → WGS 84 (EPSG:5239, „S-JTSK to WGS 84 (5)“),
přesnost přibližně 1 m – pro přesnější převod (cm) je potřeba opravná tabulka ČÚZK.
Y, X jsou kladné souřadnice S-JTSK (jak je píše Groma), zeměpisné souřadnice ve stupních.
"""

from __future__ import annotations

import math

# Besselův elipsoid
BESSEL_A = 6377397.155
BESSEL_F = 1 / 299.1528128
WGS_A = 6378137.0
WGS_F = 1 / 298.257223563

# Křovákovo zobrazení (EPSG:5514 / 2065)
PHI_C = math.radians(49.5)  # zeměpisná šířka středu
LAM_0 = math.radians(24 + 50 / 60)  # 42°30' východně od Ferra = 24°50' od Greenwiche
ALFA_C = math.radians(30.2881397527778)  # 30°17'17.30311"
PHI_P = math.radians(78.5)  # nekartografická rovnoběžka
K_P = 0.9999

# S-JTSK → WGS 84, EPSG:5239 (coordinate frame): posuny [m], rotace [″], měřítko [ppm]
HELMERT = (572.213, 85.334, 461.94, -4.9732, -1.529, -5.2484, 3.5378)

_E2 = BESSEL_F * (2 - BESSEL_F)
_E = math.sqrt(_E2)
_A = BESSEL_A * math.sqrt(1 - _E2) / (1 - _E2 * math.sin(PHI_C) ** 2)
_B = math.sqrt(1 + _E2 * math.cos(PHI_C) ** 4 / (1 - _E2))
_G0 = math.asin(math.sin(PHI_C) / _B)
_T0 = (math.tan(math.pi / 4 + _G0 / 2) * ((1 + _E * math.sin(PHI_C)) / (1 - _E * math.sin(PHI_C))) ** (_E * _B / 2)
       / math.tan(math.pi / 4 + PHI_C / 2) ** _B)
_N = math.sin(PHI_P)
_R0 = K_P * _A / math.tan(PHI_P)


def krovak(phi: float, lam: float) -> tuple[float, float]:
    """Besselovy zeměpisné souřadnice [rad] → S-JTSK (Y, X) [m]."""
    u = 2 * (math.atan(_T0 * math.tan(phi / 2 + math.pi / 4) ** _B
                       / ((1 + _E * math.sin(phi)) / (1 - _E * math.sin(phi))) ** (_E * _B / 2)) - math.pi / 4)
    v = _B * (LAM_0 - lam)
    t = math.asin(math.cos(ALFA_C) * math.sin(u) + math.sin(ALFA_C) * math.cos(u) * math.cos(v))
    d = math.asin(math.cos(u) * math.sin(v) / math.cos(t))
    theta = _N * d
    r = _R0 * math.tan(math.pi / 4 + PHI_P / 2) ** _N / math.tan(t / 2 + math.pi / 4) ** _N
    return r * math.sin(theta), r * math.cos(theta)  # Y (na západ), X (na jih)


def krovak_inv(y: float, x: float) -> tuple[float, float]:
    """S-JTSK (Y, X) [m] → Besselovy zeměpisné souřadnice [rad]."""
    r = math.hypot(x, y)
    theta = math.atan2(y, x)
    d = theta / _N
    t = 2 * (math.atan((_R0 / r) ** (1 / _N) * math.tan(math.pi / 4 + PHI_P / 2)) - math.pi / 4)
    u = math.asin(math.cos(ALFA_C) * math.sin(t) - math.sin(ALFA_C) * math.cos(t) * math.cos(d))
    v = math.asin(math.cos(t) * math.sin(d) / math.cos(u))
    lam = LAM_0 - v / _B
    phi = u
    for _ in range(20):
        nxt = 2 * (math.atan(_T0 ** (-1 / _B) * math.tan(u / 2 + math.pi / 4) ** (1 / _B)
                             * ((1 + _E * math.sin(phi)) / (1 - _E * math.sin(phi))) ** (_E / 2)) - math.pi / 4)
        if abs(nxt - phi) < 1e-14:
            phi = nxt
            break
        phi = nxt
    return phi, lam


def _geod2cart(phi, lam, h, a, f):
    e2 = f * (2 - f)
    n = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    return ((n + h) * math.cos(phi) * math.cos(lam), (n + h) * math.cos(phi) * math.sin(lam),
            (n * (1 - e2) + h) * math.sin(phi))


def _cart2geod(x, y, z, a, f):
    e2 = f * (2 - f)
    lam = math.atan2(y, x)
    p = math.hypot(x, y)
    phi = math.atan2(z, p * (1 - e2))
    for _ in range(20):
        n = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
        h = p / math.cos(phi) - n
        nxt = math.atan2(z, p * (1 - e2 * n / (n + h)))
        if abs(nxt - phi) < 1e-14:
            phi = nxt
            break
        phi = nxt
    n = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    return phi, lam, p / math.cos(phi) - n


def _helmert(x, y, z, inverse=False):
    tx, ty, tz, rx, ry, rz, s = HELMERT
    sec = math.pi / (180 * 3600)
    rx, ry, rz, m = rx * sec, ry * sec, rz * sec, 1 + s * 1e-6
    # konvence „coordinate frame“: X' = T + m·R·X, R = [[1, rz, −ry], [−rz, 1, rx], [ry, −rx, 1]]
    if not inverse:
        return (tx + m * (x + rz * y - ry * z), ty + m * (-rz * x + y + rx * z), tz + m * (ry * x - rx * y + z))
    # inverze (malé úhly): X = R^T·(X' − T)/m
    x0, y0, z0 = (x - tx) / m, (y - ty) / m, (z - tz) / m
    return (x0 - rz * y0 + ry * z0, rz * x0 + y0 - rx * z0, -ry * x0 + rx * y0 + z0)


def sjtsk_na_wgs84(y: float, x: float, h: float = 0.0) -> tuple[float, float, float]:
    """S-JTSK (Y, X kladné) + výška [m] → WGS84 (šířka, délka [°], elipsoidická výška [m] – přibližně)."""
    phi, lam = krovak_inv(abs(y), abs(x))
    cx, cy, cz = _geod2cart(phi, lam, h, BESSEL_A, BESSEL_F)
    wx, wy, wz = _helmert(cx, cy, cz)
    p, l, hh = _cart2geod(wx, wy, wz, WGS_A, WGS_F)
    return math.degrees(p), math.degrees(l), hh


def wgs84_na_sjtsk(sirka: float, delka: float, h: float = 0.0) -> tuple[float, float, float]:
    """WGS84 (šířka, délka [°], výška) → S-JTSK (Y, X kladné, výška nad Besselem [m] – přibližně)."""
    wx, wy, wz = _geod2cart(math.radians(sirka), math.radians(delka), h, WGS_A, WGS_F)
    cx, cy, cz = _helmert(wx, wy, wz, inverse=True)
    phi, lam, hb = _cart2geod(cx, cy, cz, BESSEL_A, BESSEL_F)
    y, x = krovak(phi, lam)
    return y, x, hb


def odkaz_mapy_cz(sirka: float, delka: float) -> str:
    return f"https://mapy.cz/zakladni?q={sirka:.6f}%2C{delka:.6f}"


def stupne_text(v: float, kladne: str, zaporne: str) -> str:
    """49.2196195 → 49°13'10.630"N"""
    s = kladne if v >= 0 else zaporne
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    sec = (v - d - m / 60) * 3600
    return f"{d}°{m:02d}'{sec:06.3f}\"{s}"
