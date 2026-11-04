"""Výkresy z Kokeše (GEPRO): převody čísel podle Zadání Kokeš a rozpoznání kreslícího klíče.

Ze zadání (Zadaní-Kokeš.doc):

* číslo barvy v Kokeši = číslo barvy v MicroStationu, jen barva 0 MicroStationu je v Kokeši 100;
* kreslící klíče (KK) jsou ve sloupci KK Směrnice-výběr.xls, styl 4 MicroStationu je v Kokeši −13;
* texty se barví zvláštním klíčem 1xx, kde xx je číslo barvy textu (175 = popis povrchů barvou 75);
* font 1 MicroStationu je v Kokeši font 2;
* odevzdává se Prijmeni_cz_xx.vyk (výkres) a Prijmeni_cz_xx.ss (seznam souřadnic).

Vlastní formát Kokeše (.vyk, .ss) je binární – kontroluje se jeho export do DXF/DGN (v Kokeši
export výkresu do DXF) a textový export seznamu souřadnic.
"""

from __future__ import annotations

import re

PRIPONY = (".vyk", ".vtx", ".ss")

NAVOD = (
    "Soubor {nazev} je ve vlastním formátu Kokeše – ten aplikace přímo nepřečte.\n\n"
    "Výkres: v Kokeši ho vyexportujte do DXF (export výkresu v nabídce Soubor) a DXF otevřete tady. "
    "Barvy, kreslící klíče a vrstvy se při kontrole převedou podle Zadání Kokeš (barva 100 = 0, "
    "styl −13 = 4, klíče ze sloupce KK Směrnice) – v Zadání → Pravidla nastavte „Výkres kreslen v: Kokeš“.\n\n"
    "Seznam souřadnic (.ss): v Kokeši ho vyexportujte jako textový seznam „číslo Y X Z“ a nahrajte "
    "do Zadání → Podklady nebo do Výpočtů."
)

_KLIC_ATR = ("KK", "KRESLICI_KLIC", "KRESLICIKLIC", "KLIC", "KOKES_KK")
_KLIC_TYP = re.compile(r"^(?:KK[_ ]?)?(-?\d{1,4})$", re.IGNORECASE)


def navod(nazev: str) -> str:
    return NAVOD.format(nazev=nazev)


def barva_kokes_na_ms(n: int | str | None) -> int | None:
    """Číslo barvy Kokeše → MicroStation (100 → 0, ostatní stejně)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return 0 if n == 100 else n


def styl_kokes_na_ms(s: str | None) -> str | None:
    return "4" if str(s or "").strip() == "-13" else s


def klic_prvku(f) -> int | None:
    """Kreslící klíč prvku: z atributu (KK…) nebo z názvu typu čáry („13“, „-13“, „KK13“)."""
    for k in _KLIC_ATR:
        v = (f.attributes or {}).get(k)
        if v not in (None, ""):
            try:
                return int(float(str(v).replace(",", ".")))
            except ValueError:
                pass
    m = _KLIC_TYP.match(str(f.linetype or "").strip())
    return int(m.group(1)) if m else None


def klic_v_rozsahu(vzor: str | None, klic: int) -> bool:
    """„1-4“, „20“, „1-4,9“ obsahuje klíč? (rozsahy celých čísel ze sloupce KK)."""
    if not vzor:
        return True
    for cast in re.split(r"[,;|]", str(vzor)):
        cast = cast.strip()
        m = re.match(r"^(-?\d+)\s*[-–—]\s*(-?\d+)$", cast)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if min(a, b) <= klic <= max(a, b):
                return True
        elif re.fullmatch(r"-?\d+", cast) and int(cast) == klic:
            return True
    return False


def barva_textu_z_klice(klic: int | None) -> int | None:
    """Textový klíč 1xx → barva xx (175 → 75)."""
    if klic is not None and 100 <= klic <= 199:
        return klic - 100
    return None


# ------------------------------------------------------------------ čísla bodů KN (seznam souřadnic Kokeše)
def cislo_kn(ku: str | int | None, zpmz: int, poradove: int) -> str:
    """Úplné číslo bodu KN: k.ú. (6) + ZPMZ (5) + pořadové číslo (4); bez k.ú. jen ZPMZ + číslo (9 číslic)."""
    if not 0 < int(zpmz) < 100000 or not 0 < int(poradove) < 10000:
        raise ValueError("ZPMZ má 1–5 číslic a pořadové číslo 1–4 číslice.")
    zaklad = f"{int(zpmz):05d}{int(poradove):04d}"
    if ku in (None, ""):
        return zaklad
    ku = re.sub(r"\D", "", str(ku))
    if len(ku) != 6:
        raise ValueError("Katastrální území má šestimístné číslo (např. 610844).")
    return ku + zaklad


def rozloz_cislo(cislo: str) -> tuple[str | None, int | None, int] | None:
    """„610844000130001“ → („610844“, 13, 1); „000130001“ → (None, 13, 1); „15“ → (None, None, 15)."""
    c = re.sub(r"\s", "", cislo or "")
    if not c.isdigit():
        return None
    if len(c) == 15:
        return c[:6], int(c[6:11]), int(c[11:])
    if len(c) == 9:
        return None, int(c[:5]), int(c[5:])
    if len(c) <= 4:
        return None, None, int(c)
    return None


def zkracene(cislo: str) -> str:
    """Zobrazení čísla bodu jako v Kokeši/výkresu: ZPMZ-pořadové („13-1“), krátké číslo beze změny."""
    r = rozloz_cislo(cislo)
    if r is None or r[1] is None:
        return cislo
    return f"{r[1]}-{r[2]}" if r[1] else str(r[2])


def na_cisla_kn(seznam, ku: str | None, zpmz: int, cisla: list[str] | None = None) -> int:
    """Krátká čísla (1–4 číslice) vybraných bodů → úplná čísla KN v daném ZPMZ (a k.ú.). Jedno Zpět."""
    from dataclasses import asdict

    from .geodezie.body import Bod
    vyber = set(cisla) if cisla else None
    nova = {}
    for b in seznam.body:
        if vyber is not None and b.cislo not in vyber:
            continue
        r = rozloz_cislo(b.cislo)
        if r is not None and r[1] is None:
            nova[b.cislo] = cislo_kn(ku, zpmz, r[2])
    ostatni = {b.cislo for b in seznam.body if b.cislo not in nova}
    kolize = sorted(c for c in nova.values() if c in ostatni)
    if kolize:
        raise ValueError("Čísla už v seznamu jsou: " + ", ".join(kolize[:8]))
    if not nova:
        return 0

    def fn(body):
        for i, b in enumerate(body):
            if b.cislo in nova:
                d = asdict(b)
                d["cislo"] = nova[b.cislo]
                body[i] = Bod(**d)
        return len(nova)

    return seznam.zmen(f"Čísla bodů KN (ZPMZ {zpmz})", fn, len(nova))


def seznam_text(body, desetin: int = 2) -> str:
    """Seznam souřadnic jako textový export Kokeše: číslo, Y, X, Z, kód kvality (pevné sloupce)."""
    out = []
    for b in body:
        z = "" if b.z is None else f"{b.z:.{desetin}f}"
        kk = "" if b.kvalita is None else str(b.kvalita)
        out.append(f"{b.cislo:>15} {b.y:>12.{desetin}f} {b.x:>12.{desetin}f} {z:>9} {kk:>2}".rstrip())
    return "\n".join(out) + ("\n" if out else "")


# ------------------------------------------------------------------ tabulky Kokeše ze Směrnice
def tabulky(rs, tabulka_barev: dict | None = None) -> dict:
    """Hodnoty pro tabulky, které se podle Zadání Kokeš zakládají ze Směrnice MicroStationu.

    Vrací {"barvy": [(kokes, ms, (r, g, b))], "cary": [(kk, název, hladina, barva_kokes, styl_kokes, wt)],
    "texty": [(klíč 1xx, barva, název)], "fonty": [(ms, kokes)]}."""
    from .cad import symbologie as SY
    tab = tabulka_barev or SY.tabulka(rs)
    pouzite: list[int] = []
    cary, texty, fonty = [], [], set()
    for r in rs.pravidla:
        barvy = [int(c) for c in str(r.barva).split("|") if c.strip().isdigit()] if r.barva is not None else []
        for c in barvy:
            if c not in pouzite:
                pouzite.append(c)
        if r.geometrie is not None and r.geometrie.value == "text":
            for c in barvy:
                texty.append((100 + c, c, r.nazev or r.kod))
            if r.font:
                fonty.add(r.font)
            continue
        if r.kreslici_klic:
            styl = str(r.styl_cary or "0")
            styl_k = ",".join("-13" if s.strip() == "4" else s.strip() for s in re.split(r"[,|]", styl) if s.strip())
            cary.append((r.kreslici_klic, r.nazev or r.kod, r.hladina or "",
                         ",".join(str(100 if c == 0 else c) for c in barvy), styl_k,
                         "" if r.tloustka is None else str(r.tloustka)))
    barvy_out = [(100 if c == 0 else c, c, tuple(tab.get(c, (0, 0, 0)))) for c in sorted(pouzite)]
    videno, texty_u = set(), []
    for t in sorted(texty):
        if t[0] not in videno:
            videno.add(t[0])
            texty_u.append(t)
    return {"barvy": barvy_out, "cary": cary, "texty": texty_u,
            "fonty": [("1", "2")] + [(f, f) for f in sorted(fonty)]}


def tabulky_html(rs, nazev: str = "Tabulky pro Kokeš") -> str:
    import html as H
    t = tabulky(rs)
    radky = lambda rr: "".join("<tr>" + "".join(f"<td>{H.escape(str(x))}</td>" for x in r) + "</tr>"  # noqa: E731
                               for r in rr)
    barvy = "".join(f"<tr><td>{k}</td><td>{m}</td><td>{c[0]}</td><td>{c[1]}</td><td>{c[2]}</td>"
                    f"<td style='background:rgb{c};width:3em'></td></tr>" for k, m, c in t["barvy"])
    return (f"<!doctype html><meta charset='utf-8'><title>{H.escape(nazev)}</title>"
            "<style>body{font-family:sans-serif;margin:24px}table{border-collapse:collapse;margin-bottom:24px}"
            "td,th{border:1px solid #bbb;padding:3px 8px}th{background:#eee}</style>"
            f"<h1>{H.escape(nazev)}</h1><p>Podle Zadání Kokeš: číslo barvy v Kokeši = číslo barvy MicroStationu, "
            "barva 0 → 100; styl 4 → −13; texty se barví klíčem 1xx (xx = barva); font 1 → 2. "
            "Tabulky založte z obecných tabulek Kokeše, pojmenujte bez diakritiky a připojte k výkresu "
            "(Soubor → Připojení tabulek k výkresu).</p>"
            "<h2>Tabulka barev</h2><table><tr><th>Kokeš</th><th>MicroStation</th><th>R</th><th>G</th><th>B</th>"
            f"<th></th></tr>{barvy}</table>"
            "<h2>Tabulka čar (kreslící klíče)</h2><table><tr><th>KK</th><th>Prvek</th><th>Hladina</th>"
            f"<th>Barva</th><th>Styl</th><th>Tloušťka (wt)</th></tr>{radky(t['cary'])}</table>"
            "<h2>Klíče pro obarvení textů</h2><table><tr><th>Klíč</th><th>Barva</th><th>Text</th></tr>"
            f"{radky(t['texty'])}</table>"
            "<h2>Fonty</h2><table><tr><th>MicroStation</th><th>Kokeš</th></tr>"
            f"{radky(t['fonty'])}</table>")
