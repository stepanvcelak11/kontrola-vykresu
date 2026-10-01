"""Výkres podle zadání: z pravidel učitele (Směrnice, Word zadání, vzorový výkres) připraví CAD.

* ``predvolby(rs)``: pro každý druh prvku z pravidel (kód) předvolba atributů: vrstva, barva, styl čáry,
  tloušťka, textový styl, výška a šířka písma, zarovnání a nástroj, kterým se kreslí.
* ``priprav_dokument(doc, rs, vzory)``: založí ve výkresu všechny vrstvy, typy čar, textové styly
  a převezme bloky (buňky) ze vzorových výkresů.

Atributy se převádějí stejně, jak je pak čte Kontrola výkresu (a jak je do DXF ukládá MicroStation):
barva MicroStationu → RGB z tabulky barev → nejbližší ACI, tloušťka MicroStationu → mm podle převodní
tabulky, styl čáry 0–7 → typ čáry s číslem stylu. Výkres nakreslený podle předvoleb proto projde
kontrolou symbologie bez chyb.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..model import GeomType
from ..rules import RuleSet, color_rgb, rgb_to_aci, split_alternatives

# DXF povoluje jen tyto tloušťky (setiny mm)
_DXF_TLOUSTKY = (0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211)

# styly čar MicroStationu 0–7 jako typy čar DXF (vzory v metrech na papíře × LTSCALE)
MS_STYLY = {
    1: ("MicroStation styl 1 – tečkovaná", [0.6, 0.0, -0.6]),
    2: ("MicroStation styl 2 – čárkovaná střední", [3.0, 2.0, -1.0]),
    3: ("MicroStation styl 3 – čárkovaná dlouhá", [5.0, 4.0, -1.0]),
    4: ("MicroStation styl 4 – čerchovaná", [4.0, 2.5, -0.5, 0.0, -1.0]),
    5: ("MicroStation styl 5 – čárkovaná krátká", [1.5, 1.0, -0.5]),
    6: ("MicroStation styl 6 – dvojčerchovaná", [4.5, 2.5, -0.5, 0.0, -0.5, 0.0, -1.0]),
    7: ("MicroStation styl 7 – dlouhá a krátká čárka", [5.0, 3.0, -0.5, 1.0, -0.5]),
}

_ZAROVNANI = {(0, 0): "LEFT", (1, 0): "CENTER", (2, 0): "RIGHT", (0, 1): "BOTTOM_LEFT", (1, 1): "BOTTOM_CENTER",
              (2, 1): "BOTTOM_RIGHT", (0, 2): "MIDDLE_LEFT", (1, 2): "MIDDLE_CENTER", (2, 2): "MIDDLE_RIGHT",
              (0, 3): "TOP_LEFT", (1, 3): "TOP_CENTER", (2, 3): "TOP_RIGHT"}


@dataclass
class Predvolba:
    nazev: str
    geometrie: str  # bod | linie | polygon | text | None
    nastroj: str  # příkaz CAD: bod, polylinie, text, vlož…
    vrstva: str = "0"
    barva: int = 256  # ACI
    typ_cary: str = "BYLAYER"
    tloustka: int = -1  # setiny mm, −1 = BYLAYER
    textovy_styl: str | None = None
    vyska: float | None = None  # m ve výkresu
    sirka_faktor: float = 1.0
    zarovnani: str | None = None  # TextEntityAlignment
    blok: str | None = None  # povolené buňky (vzor), např. „4.01–4.20“
    meritko_stylu: float | None = None
    poznamky: list[str] = field(default_factory=list)
    kod: str = ""
    font: str | None = None  # font z pravidla i se souborem, např. „Arial Narrow IF (ARIALNI.TTF)“
    tucne: bool = False
    kurziva: bool = False
    ms: dict = field(default_factory=dict)  # původní hodnoty z pravidla (čísla MicroStationu) pro key-in

    def popis(self) -> str:
        r = [f"vrstva {self.vrstva}"]
        if self.barva != 256:
            r.append(f"barva ACI {self.barva}")
        if self.typ_cary not in ("BYLAYER", "CONTINUOUS"):
            r.append(f"styl {self.typ_cary}")
        if self.tloustka >= 0:
            r.append(f"tloušťka {self.tloustka / 100:.2f} mm")
        if self.vyska:
            r.append(f"výška písma {self.vyska:.3f} m")
        if self.textovy_styl:
            r.append(f"písmo {self.textovy_styl}")
        if self.zarovnani:
            r.append(self.zarovnani.lower().replace("_", " "))
        return ", ".join(r)


def _prvni(v) -> str | None:
    alts = split_alternatives(v) if v not in (None, "") else []
    return alts[0].strip() if alts else None


def _vrstva(hladina) -> str:
    v = _prvni(hladina) or "0"
    v = re.split(r"\s*[–—]\s*|\s+-\s+", v)[0]  # rozsah hladin → první
    return v.replace("*", "").replace("?", "") or "0"


def _aci(barva, rs: RuleSet) -> tuple[int, str | None]:
    v = barva
    if isinstance(v, str) and "|" in v:
        v = v.split("|")[0]
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        v = int(v)
    if v is None or v == "":
        return 7, None  # pravidlo barvu neurčuje: pevná bílá/černá, ne „dle vrstvy“ (to kontrola hlásí)
    if rs.paleta == "autocad" and isinstance(v, int):
        return (v if 1 <= v <= 255 else 7), None
    rgb = color_rgb(v, rs.paleta, rs.barevna_tabulka)
    if rgb is None:
        return 7, f"barvu {barva} nejde převést (chybí tabulka barev color.tbl) – nastavte ji ručně"
    return min(rgb_to_aci(tuple(rgb))), None


def _typ_cary(styl) -> tuple[str, str | None]:
    s = _prvni(styl)
    if not s:
        return "CONTINUOUS", None
    if s.isdigit():
        n = int(s)
        if n == 0:
            return "CONTINUOUS", None
        if n in MS_STYLY:
            return f"MS{n}", None
    m = re.match(r"^(\d+\.[0-9A-Za-z]+)", s)
    if m:  # vlastní styl MicroStationu (z rozsahu „2.09–2.17“ první) – typ čáry se jménem kódu stylu
        return m.group(1), None
    return s.upper(), None


def _tloustka(rule, rs: RuleSet) -> tuple[int, str | None]:
    if rule.tloustka is None:
        return 0, None
    exp, unknown = rs.expected_weights(rule)
    if not exp:
        return 0, (f"tloušťka MicroStationu {', '.join(map(str, unknown))} nemá převod na mm – doplňte "
                    "převodní tabulku tloušťek" if unknown else None)
    mm = exp[0]
    return min(_DXF_TLOUSTKY, key=lambda t: abs(t / 100 - mm)), None


def _nazev_stylu(font: str) -> str:
    s = re.sub(r"\s*\([^)]*\)\s*$", "", font).strip() or font
    return re.sub(r'[<>/\\":;?*|=`]', "_", s)[:250]


def predvolby(rs: RuleSet) -> list[Predvolba]:
    out = []
    for r in rs.pravidla:
        geo = r.geometrie.value if isinstance(r.geometrie, GeomType) else (r.geometrie or None)
        if geo is None and (r.font or r.vyska_textu):
            geo = "text"
        nastroj = {"bod": "bod", "linie": "polylinie", "polygon": "polylinie", "text": "text"}.get(geo, "polylinie")
        if r.blok:
            nastroj = "vlož"
        p = Predvolba(nazev=r.nazev or r.kod or (r.hladina or "?"), kod=r.kod or "", geometrie=geo,
                      nastroj=nastroj, vrstva=_vrstva(r.hladina), blok=r.blok, meritko_stylu=r.meritko_stylu)
        p.ms = {"vrstva": p.vrstva, "barva": _prvni(r.barva) if r.barva not in (None, "") else None,
                "styl": _prvni(r.styl_cary), "tloustka": _prvni(r.tloustka) if r.tloustka is not None else None,
                "font": r.font, "vyska": p.vyska if geo == "text" else None,
                "sirka": rs.text_size(r.sirka_textu) if (geo == "text" and r.sirka_textu) else None,
                "blok": _prvni(r.blok)}
        if not r.hladina:
            p.poznamky.append("pravidlo neurčuje vrstvu – kreslí se do vrstvy 0, doplňte vrstvu v Zadání → Pravidla")
        p.barva, pozn = _aci(r.barva, rs)
        if pozn:
            p.poznamky.append(pozn)
        if geo != "text":
            p.typ_cary, pozn = _typ_cary(r.styl_cary)
            if pozn:
                p.poznamky.append(pozn)
            p.tloustka, pozn = _tloustka(r, rs)
            if pozn:
                p.poznamky.append(pozn)
        else:
            if r.font:
                p.font = r.font
                p.tucne, p.kurziva = bool(r.tucne), bool(r.kurziva)
                p.textovy_styl = _nazev_stylu(r.font) + (" Bold" if p.tucne else "") + (" Italic" if p.kurziva
                                                                                       else "")
            p.vyska = rs.text_size(r.vyska_textu) if r.vyska_textu else None
            if r.sirka_textu and p.vyska:
                p.sirka_faktor = rs.text_size(r.sirka_textu) / p.vyska
            if r.zarovnani:
                from ..checks.attributes import parse_alignment
                h, v = parse_alignment(r.zarovnani)
                p.zarovnani = _ZAROVNANI.get((h if h is not None else 0, v if v is not None else 0))
        if r.kod and r.kod != p.nazev:
            p.nazev = f"{r.kod} – {r.nazev}" if r.nazev else r.kod
        out.append(p)
    return out


def priprav_dokument(doc, rs: RuleSet, vzory: list[str | Path] = ()) -> list[str]:
    """Vrstvy, typy čar, textové styly a bloky ze vzorových výkresů. Vrací zprávu, co se připravilo."""
    zprava = []
    pv = predvolby(rs)
    # typy čar MicroStationu
    pouzite = {p.typ_cary for p in pv}
    for n, (popis, vzor) in MS_STYLY.items():
        if f"MS{n}" in pouzite and f"MS{n}" not in doc.linetypes:
            doc.linetypes.add(f"MS{n}", pattern=vzor, description=popis)
    for p in pv:
        if re.match(r"^\d+\.[0-9A-Za-z]+$", p.typ_cary) and p.typ_cary not in doc.linetypes:
            doc.linetypes.add(p.typ_cary, pattern=[3.0, 2.0, -0.5, 0.0, -0.5],
                              description=f"Vlastní styl MicroStationu {p.typ_cary} (vzhled jen přibližný)")
            p.poznamky.append(f"styl {p.typ_cary} je vlastní styl MicroStationu – v CAD má přibližný vzhled")
    for p in pv:
        if p.typ_cary not in ("BYLAYER", "CONTINUOUS") and p.typ_cary not in doc.linetypes:
            p.poznamky.append(f"typ čáry {p.typ_cary} ve výkresu není – použije se plná")
            p.typ_cary = "CONTINUOUS"
    # vrstvy
    nove = []
    for name in [p.vrstva for p in pv] + [str(v) for v in rs.povolene_hladiny]:
        name = _vrstva(name)
        if name and name not in doc.layers:
            doc.layers.add(name)
            nove.append(name)
    if nove:
        zprava.append(f"Vrstvy ({len(nove)}): " + ", ".join(sorted(nove, key=_klic)[:60])
                      + ("…" if len(nove) > 60 else ""))
    # textové styly
    styly = []
    for p in pv:
        if p.textovy_styl and p.textovy_styl not in doc.styles:
            font = p.font or p.textovy_styl
            m = re.search(r"\(([^()]*\.(?:shx|ttf|otf))\)\s*$", font, re.I)
            if m:
                soubor = m.group(1)
            elif re.search(r"\.(shx|ttf|otf)$", font, re.I):
                soubor = font
            else:
                soubor = _soubor_fontu(font, p.tucne, p.kurziva)
            doc.styles.add(p.textovy_styl, font=soubor)
            styly.append(p.textovy_styl)
    if styly:
        zprava.append("Textové styly: " + ", ".join(styly))
    # bloky ze vzorových výkresů
    bloky = prevezmi_bloky(doc, vzory) if vzory else []
    if bloky:
        zprava.append(f"Buňky ze vzorového výkresu ({len(bloky)}): " + ", ".join(bloky[:30])
                      + ("…" if len(bloky) > 30 else ""))
    doc.header["$INSUNITS"] = 6
    if rs.meritko:
        doc.header["$LTSCALE"] = rs.meritko / 1000.0
    return zprava


def prevezmi_bloky(doc, vzory) -> list[str]:
    """Definice bloků (buněk) ze vzorových DXF – kreslí se pak stejné značky jako ve vzoru."""
    import ezdxf
    from ezdxf.addons import importer
    out = []
    for f in vzory:
        if Path(f).suffix.lower() != ".dxf":
            continue
        try:
            src = ezdxf.readfile(f)
        except Exception:  # noqa: BLE001
            continue
        jmena = [b.name for b in src.blocks if not b.name.startswith("*") and not b.is_any_layout
                 and b.name not in doc.blocks]
        if not jmena:
            continue
        imp = importer.Importer(src, doc)
        imp.import_blocks(jmena)
        imp.finalize()
        out += jmena
    return out


# soubory řezů běžných fontů Windows (obyčejné, tučné, kurzíva, tučná kurzíva)
_REZY = {"arial narrow": ("ARIALN.TTF", "ARIALNB.TTF", "ARIALNI.TTF", "ARIALNBI.TTF"),
         "arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
         "times new roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
         "calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf")}


def _soubor_fontu(font: str, tucne: bool, kurziva: bool) -> str:
    low = font.lower().strip()
    for name, rezy in _REZY.items():
        if low.startswith(name):
            return rezy[(1 if tucne else 0) + (2 if kurziva else 0)]
    return re.sub(r"\s+", "_", low) + ".shx"


def keyin(p: Predvolba) -> str:
    """Řetězec key-in MicroStationu, který nastaví aktivní atributy pro druh prvku (vloží se do okna Key-in).

    LV = hladina, CO = barva, LC = styl čáry, WT = tloušťka, TH/TW = výška/šířka textu, AC = aktivní buňka."""
    m = p.ms or {}
    r = [f"lv={m.get('vrstva') or p.vrstva}"]
    if m.get("barva") not in (None, ""):
        r.append(f"co={m['barva']}")
    if p.geometrie != "text":
        st = m.get("styl")
        if st:
            n = st.upper()
            r.append("lc=0" if n in ("CONTINUOUS", "SOLID", "PLNÁ", "PLNA") else f"lc={st}")
        if m.get("tloustka") not in (None, ""):
            w = str(m["tloustka"]).replace(".0", "") if str(m["tloustka"]).endswith(".0") else m["tloustka"]
            r.append(f"wt={w}")
    else:
        if m.get("vyska"):
            r.append(f"th={_cislo(m['vyska'])}")
        if m.get("sirka"):
            r.append(f"tw={_cislo(m['sirka'])}")
        elif m.get("vyska"):
            r.append(f"tw={_cislo(m['vyska'])}")
    if m.get("blok") and not re.search(r"[–—]|\s-\s", str(m["blok"])):
        r.append(f"ac={m['blok']}")
    return ";".join(r)


def _cislo(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def tahak_html(rs: RuleSet, nazev: str = "Atributy podle zadání") -> str:
    """Tahák atributů pro MicroStation i CAD: co nastavit pro který prvek, s řádkem key-in ke zkopírování."""
    from html import escape
    radky = []
    for p in predvolby(rs):
        m = p.ms or {}
        pismo = ""
        if p.geometrie == "text":
            pismo = escape(p.font or "") + (f", výška {_cislo(p.vyska)} m" if p.vyska else "")
            pismo += (" tučně" if p.tucne else "") + (" kurzíva" if p.kurziva else "")
            if p.zarovnani:
                pismo += ", " + p.zarovnani.lower().replace("_", " ")
        radky.append(
            f"<tr><td>{escape(p.kod)}</td><td>{escape(p.nazev)}</td><td>{escape(p.geometrie or '')}</td>"
            f"<td>{escape(str(m.get('vrstva') or p.vrstva))}</td><td>{escape(str(m.get('barva') if m.get('barva') is not None else '–'))}</td>"
            f"<td>{escape(str(m.get('styl') or '–'))}</td><td>{escape(str(m.get('tloustka') if m.get('tloustka') is not None else '–'))}</td>"
            f"<td>{pismo or '–'}</td><td>{escape(str(m.get('blok') or ''))}</td>"
            f"<td><code>{escape(keyin(p))}</code></td>"
            f"<td>{'<br>'.join(escape(x) for x in p.poznamky)}</td></tr>")
    return f"""<!doctype html><html lang="cs"><head><meta charset="utf-8"><title>{escape(nazev)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:16px;color:#111}}table{{border-collapse:collapse;width:100%;font-size:12px}}
th,td{{border:1px solid #ccc;padding:4px 6px;vertical-align:top}}th{{background:#f1f5f9;text-align:left}}
code{{background:#f1f5f9;padding:1px 4px;user-select:all}}tr:nth-child(even) td{{background:#fafafa}}
@media print{{body{{margin:0}}}}</style></head><body>
<h1>{escape(nazev)}</h1>
<p>Barvy, styly a tloušťky jsou čísla MicroStationu. Řádek <b>key-in</b> zkopírujte do okna Key-in v MicroStationu
(Utilities → Key-in) a Enter – nastaví aktivní hladinu, barvu, styl a tloušťku (u textů výšku a šířku písma) najednou.
V CAD této aplikace stačí zvolit prvek v poli „Kreslím“.</p>
<table><tr><th>Kód</th><th>Prvek</th><th>Geometrie</th><th>Hladina</th><th>Barva</th><th>Styl</th><th>Tloušťka</th>
<th>Písmo</th><th>Buňka</th><th>Key-in</th><th>Poznámka</th></tr>
{''.join(radky)}</table></body></html>"""


def _klic(s: str):
    return (0, int(s), "") if s.isdigit() else (1, 0, s.lower())


def novy_dokument(rs: RuleSet, vzory=()):
    from .dokument import CadDokument
    d = CadDokument()
    zprava = priprav_dokument(d.doc, rs, vzory)
    d._souhrn()
    return d, zprava
