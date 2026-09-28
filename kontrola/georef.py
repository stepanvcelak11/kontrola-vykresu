"""Umístění obrázku (náčrt, sken, PDF vzoru) pod výkres podle dvou identických bodů.

Obrázek se umisťuje podobnostní transformací (posun, měřítko, natočení):

    svět = P0 + s · R(θ) · (u, h − v)

kde (u, v) jsou pixely obrázku (v roste dolů), h je výška obrázku, P0 je levý dolní roh
obrázku v souřadnicích výkresu, s je měřítko v m/px a θ natočení proti směru hodinových ručiček.
Stejné parametry používá zobrazení podkladu (x, y, měřítko, rotace).
"""

from __future__ import annotations

import math


def similarity_from_two_points(img1: tuple[float, float], img2: tuple[float, float],
                               world1: tuple[float, float], world2: tuple[float, float],
                               image_height: float) -> dict:
    """Vrátí parametry podkladu {x, y, meritko, rotace} z dvojice identických bodů."""
    q1 = complex(img1[0], image_height - img1[1])
    q2 = complex(img2[0], image_height - img2[1])
    w1 = complex(*world1)
    w2 = complex(*world2)
    if abs(q2 - q1) < 1e-9:
        raise ValueError("Body v obrázku jsou totožné – zvolte dva různé body.")
    if abs(w2 - w1) < 1e-9:
        raise ValueError("Body ve výkresu jsou totožné – zvolte dva různé body.")
    z = (w2 - w1) / (q2 - q1)
    p0 = w1 - z * q1
    return {"x": p0.real, "y": p0.imag, "meritko": abs(z), "rotace": math.degrees(math.atan2(z.imag, z.real))}


def image_to_world(params: dict, u: float, v: float, image_height: float) -> tuple[float, float]:
    s, th = params["meritko"], math.radians(params["rotace"])
    qx, qy = u, image_height - v
    return (params["x"] + s * (math.cos(th) * qx - math.sin(th) * qy),
            params["y"] + s * (math.sin(th) * qx + math.cos(th) * qy))
