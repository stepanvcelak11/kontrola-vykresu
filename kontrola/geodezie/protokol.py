"""Výpočetní protokol polární metody dávkou – oddíly a sloupce jako v běžných geodetických programech
(import souřadnic, kontrola číslování, import měření, redukce délek, refrakce a zakřivení, opakovaná
měření, polární metoda dávkou s orientací, kontrolní určení, výsledný seznam).

Protokol je čitelný text s pevnou šířkou sloupců; do PDF se převede stejně (strana, hlavička).
V hlavičce je vždy uveden program, kterým byl protokol vytvořen.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from pathlib import Path

from ..checks.seznam import ListPoint
from ..vypocet import GON, K_REFR, R_EARTH, Result, Station

PROGRAM = "Kontrola výkresu – Výpočty"
CARA = "-" * 79


def _nadpis(t: str) -> list[str]:
    return ["", t, "=" * len(t)]


def _pod(t: str) -> list[str]:
    return [t, "-" * len(t)]


def _c(v: float | None, d: int = 3, w: int = 0) -> str:
    s = "" if v is None else f"{v:.{d}f}"
    return s.rjust(w) if w else s


def oddil_import_souradnic(body: list[ListPoint], soubor: str = "") -> list[str]:
    r = _nadpis("IMPORT SOUŘADNIC")
    if soubor:
        r.append(f"Název vstupního souboru : {soubor}")
    r += _pod("STATISTIKA:")
    zs = [b.z for b in body if b.z is not None]
    ys = [abs(b.a) for b in body]
    xs = [abs(b.b) for b in body]
    cis = sorted(b.cislo for b in body)
    r += [f"Počet položek vstupního souboru: {len(body)}",
          f"Počet bodů s výškou / bez výšky: {len(zs)} / {len(body) - len(zs)}"]
    if body:
        r += [f"Číslo min / Číslo max         : {cis[0]} / {cis[-1]}",
              f"Y min / Y max                 : {min(ys):.3f} / {max(ys):.3f}",
              f"X min / X max                 : {min(xs):.3f} / {max(xs):.3f}"]
    if zs:
        r.append(f"Z min / Z max                 : {min(zs):.3f} / {max(zs):.3f}")
    return r


def oddil_cislovani(body: list[ListPoint]) -> list[str]:
    r = _nadpis("KONTROLA ČÍSLOVÁNÍ BODŮ")
    dup = [c for c, n in Counter(b.cislo for b in body).items() if n > 1]
    r.append(f"Počet duplicitních položek: {len(dup)}")
    for c in dup:
        r.append(f"  duplicitní číslo: {c}")
    return r


def _vc_obvykla(st: Station) -> float:
    c = Counter(round(o.vc, 3) for o in st.detail + st.orient)
    return c.most_common(1)[0][0] if c else 0.0


def oddil_import_mereni(stanoviska: list[Station], koeficient: float, soubor: str = "") -> list[str]:
    r = _nadpis("IMPORT MĚŘENÍ")
    if soubor:
        r.append(f"Název vstupního souboru : {soubor}")
    r.append(f"Měřítkový koeficient    : {koeficient:.10f} ({(koeficient - 1) * 1e5:+.1f} mm/100m)")
    for st in stanoviska:
        obv = _vc_obvykla(st)
        for o in st.orient + st.detail:
            if abs(o.vc - obv) > 1e-6 and (o.vc == 0 or abs(o.vc - obv) > 0.3):
                r.append(f"Stanovisko {st.bod}, bod {o.bod}: Podezřelá výška signálu : {o.vc:.3f} m "
                         f"(obvyklá {obv:.3f} m)")
    vse = [o for st in stanoviska for o in st.orient + st.detail]
    r += _pod("STATISTIKA:")
    if vse:
        r += [f"Počet položek                 : {len(vse)}",
              f"Počet stanovisek              : {len(stanoviska)}",
              f"Počet bodů se šikmou délkou   : {sum(1 for o in vse if o.sd > 0)}",
              f"Počet bodů se zenitovým úhlem : {sum(1 for o in vse if o.z)}",
              f"Počet měření v I/II poloze    : {sum(1 for o in vse if o.n == 1)} / "
              f"{sum(1 for o in vse if o.n > 1)}",
              f"Z min / Z max                 : {min(o.z for o in vse):.4f} / {max(o.z for o in vse):.4f}",
              f"Délka min / Délka max         : {min(o.sd for o in vse):.3f} / {max(o.sd for o in vse):.3f}",
              f"Signál min / Signál max       : {min(o.vc for o in vse):.3f} / {max(o.vc for o in vse):.3f}"]
    return r


def oddil_redukce(stanoviska: list[Station]) -> list[str]:
    r = _nadpis("REDUKCE ŠIKMÝCH DÉLEK NA VODOROVNÉ")
    r += [f"{'Stanovisko':<17} {'Bod':<17} {'Z':>9} {'dH':>8} {'Šikmá D':>9} {'Vod. D':>9}", CARA]
    for st in stanoviska:
        for o in st.orient + st.detail:
            if o.sd <= 0:
                continue
            d = o.sd * math.sin(o.z * GON)
            r.append(f"{st.bod:<17} {o.bod:<17} {o.z:>9.4f} {o.sd * math.cos(o.z * GON):>8.3f} {o.sd:>9.3f} "
                     f"{d:>9.3f}")
    return r


def oddil_refrakce(stanoviska: list[Station]) -> list[str]:
    r = _nadpis("OPRAVA VLIVU REFRAKCE A ZAKŘIVENÍ ZEMĚ")
    r.append(f"Koeficient refrakce k = {K_REFR:.2f}, poloměr Země R = {R_EARTH:.1f} m, oprava = d²·(1−k)/(2R)")
    r += [f"{'Stanovisko':<17} {'Bod':<17} {'Vod. D':>9} {'Oprava [mm]':>12}", CARA]
    for st in stanoviska:
        for o in st.orient + st.detail:
            d = o.sd * math.sin(o.z * GON)
            r.append(f"{st.bod:<17} {o.bod:<17} {d:>9.3f} {d * d * (1 - K_REFR) / (2 * R_EARTH) * 1000:>12.1f}")
    return r


def oddil_opakovana(stanoviska: list[Station]) -> list[str]:
    r = _nadpis("ZPRACOVÁNÍ OPAKOVANÝCH MĚŘENÍ")
    r += [f"{'Stanovisko':<17} {'Bod':<17} {'Počet':>5} {'dHz [cc]':>9} {'Index z [cc]':>12} {'dD [mm]':>8}", CARA]
    n = 0
    for st in stanoviska:
        for o in st.orient + st.detail:
            if o.n > 1:
                n += 1
                r.append(f"{st.bod:<17} {o.bod:<17} {o.n:>5} "
                         f"{'' if o.d_hz is None else f'{o.d_hz * 1e4:.0f}':>9} "
                         f"{'' if o.index_z is None else f'{o.index_z * 1e4:.0f}':>12} "
                         f"{'' if o.d_sd is None else f'{o.d_sd * 1e3:.0f}':>8}")
    if not n:
        r.append("Žádná opakovaná měření (měřeno v jedné poloze).")
    return r


def oddil_polarni(res: Result, kody_kvality: dict[str, int] | None = None) -> list[str]:
    kody_kvality = kody_kvality or {}
    r = _nadpis("POLÁRNÍ METODA DÁVKOU")
    for s in res.protokol:
        r += ["", *_pod(f"Orientace osnovy na bodě {s['stanovisko']}"),
              f"{'Bod':<17} {'Y':>12} {'X':>13} {'Z':>9} {'Kv.':>4}  Popis", CARA,
              f"{s['stanovisko']:<17} {s['y']:>12.3f} {s['x']:>13.3f} {_c(s['z'], 3, 9)}", CARA,
              *_pod("Orientace:"),
              f"{'Bod':<17} {'Y':>12} {'X':>13} {'Z':>9} {'Kv.':>4}  Popis", CARA]
        for o in s["orientace"]:
            kp = o["kp"]
            r.append(f"{o['bod']:<17} {abs(kp.a):>12.3f} {abs(kp.b):>13.3f} {_c(kp.z, 3, 9)}")
        r += [CARA, f"{'Bod':<17} {'Hz':>9} {'Váha':>5} {'Směrník':>9} {'V or.':>8} {'Délka':>9} "
                    f"{'V délky':>8} {'V přev.':>8}", CARA]
        for o in s["orientace"]:
            r.append(f"{o['bod']:<17} {o['hz']:>9.4f} {o.get('vaha', 0):>5.1f} {o['smernik']:>9.4f} "
                     f"{o.get('v_or', 0):>8.4f} {o.get('delka_mer', o['delka']):>9.3f} {_c(o['v_delky'], 3, 8)} "
                     f"{_c(o['v_prev'], 3, 8)}")
        r += [CARA,
              f"Orientační posun [g]: {s['posun']:.4f} (Směrník nulového směru)"]
        if s["m0"] is not None:
            r += [f"m0 = SQRT([vv]/(n-1)) [g]: {s['m0']:.4f} (Střední chyba jednoho orientačního směru)",
                  f"SQRT([vv]/(n*(n-1))) [g]: {s['m_posun']:.4f} (Střední chyba orientačního posunu)"]
        for o in s["orientace"]:
            if o["v_prev"] is not None and abs(o["v_prev"]) > 0.03:
                r += [f"Překročena tolerance: Oprava převýšení na orientaci {o['bod']}: {o['v_prev']:.3f} m "
                      "(mezní 0.030 m)"]
            if o["v_delky"] is not None and abs(o["v_delky"]) > max(0.03, 0.0002 * o["delka"]):
                r += [f"Překročena tolerance: Oprava délky na orientaci {o['bod']}: {o['v_delky']:.3f} m"]
        r += ["", "Podrobné body", "Polární metoda",
              f"{'Bod':<17} {'Hz':>9} {'Z':>9} {'dH':>8} {'V cíle':>7} {'Délka':>9} {'Y':>12} {'X':>13} "
              f"{'Z':>9}  Popis", "-" * 105]
        for d in s["detail"]:
            r.append(f"{d['bod']:<17} {d['hz']:>9.4f} {d['z_uhel']:>9.4f} {d['dh']:>8.3f} {d['vc']:>7.3f} "
                     f"{d['delka']:>9.3f} {d['y']:>12.3f} {d['x']:>13.3f} {_c(d['z'], 3, 9)}"
                     + ("  kontrolní určení" if d["kontrolni"] else ""))
    return r


def oddil_kontroly(res: Result) -> list[str]:
    r = _nadpis("KONTROLY MĚŘENÍ")
    if not res.kontroly:
        return r + ["Bez kontrol."]
    r += [f"{'Kontrola':<22} {'Stanovisko':<17} {'Bod':<17} {'Hodnota':<22} Výsledek", CARA]
    for k in res.kontroly:
        r.append(f"{k.druh:<22} {k.stanovisko:<17} {k.bod:<17} {k.hodnota:<22} {'vyhovuje' if k.ok else 'NEVYHOVUJE'}")
    return r


def oddil_seznam(res: Result) -> list[str]:
    r = _nadpis("SEZNAM SOUŘADNIC")
    r += [f"{'Bod':<17} {'Y':>12} {'X':>13} {'Z':>9}", CARA]
    for p in res.body:
        if p.kontrolni:
            continue
        r.append(f"{p.bod:<17} {p.y:>12.3f} {p.x:>13.3f} {_c(p.z, 3, 9)}")
    return r


def protokol_polarni(res: Result, stanoviska: list[Station], dane: list[ListPoint], *, nazev: str = "",
                     autor: str = "", soubor_souradnic: str = "", soubor_mereni: str = "") -> str:
    """Celý výpočetní protokol polární metody dávkou jako text."""
    hlav = [f"{nazev or 'Výpočetní protokol'} – výpočetní protokol ({PROGRAM})"
            + (f"  {autor}" if autor else ""),
            f"Vytvořeno: {dt.datetime.now():%d.%m.%Y %H:%M}"]
    r = hlav
    r += oddil_import_souradnic(dane, soubor_souradnic)
    r += oddil_cislovani(dane)
    r += oddil_import_mereni(stanoviska, res.koeficient, soubor_mereni)
    r += oddil_redukce(stanoviska)
    r += oddil_refrakce(stanoviska)
    r += oddil_opakovana(stanoviska)
    r += oddil_polarni(res)
    r += oddil_kontroly(res)
    r += oddil_seznam(res)
    for z in res.zpravy:
        if z.startswith("Výška stanoviska"):
            r.append(z)
    return "\n".join(r) + "\n"


def protokol_pdf(text: str, path: str | Path, nazev: str = "", autor: str = "") -> Path:
    """Text protokolu do PDF: neproporcionální písmo, hlavička se stranou na každé stránce."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    from ..export.pdf_report import _font
    font = "Courier"
    # písmo s diakritikou (Consolas / DejaVu Sans Mono), jinak Courier
    for cand in ("C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                 "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"):
        if Path(cand).exists():
            try:
                pdfmetrics.registerFont(TTFont("Mono", cand))
                font = "Mono"
                break
            except Exception:  # noqa: BLE001
                continue
    hfont = _font()[0]
    lines = text.splitlines()
    w, h = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(nazev or "Výpočetní protokol")
    size, lead = 6.6, 8.2
    top, bottom, left = h - 40, 36, 28
    per = int((top - bottom) / lead)
    pages = max(1, math.ceil(len(lines) / per))
    for pi in range(pages):
        c.setFont(hfont, 8)
        c.drawString(left, h - 24, f"{nazev or 'Výpočetní protokol'} – výpočetní protokol ({PROGRAM})"
                     + (f"   {autor}" if autor else ""))
        c.drawRightString(w - left, h - 24, f"strana {pi + 1}")
        c.setFont(font, size)
        y = top
        for ln in lines[pi * per:(pi + 1) * per]:
            c.drawString(left, y, ln)
            y -= lead
        c.showPage()
    c.save()
    return Path(path)
