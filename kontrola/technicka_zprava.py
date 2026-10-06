"""Kostra technické zprávy k účelové mapě (Pokyn pro tvorbu ÚM, kap. 7) – předvyplněná z projektu.

Co aplikace ví (projekt, počet bodů a stanovisek, rozsah, souřadnicový a výškový systém, výkres), doplní;
ostatní zůstane jako „[doplňte …]“. Uloží se jako .docx (otevře Word i LibreOffice) nebo .txt.
"""

from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

DOPLNTE = "[doplňte]"


def osnova(udaje: dict) -> list[tuple[str, list[str]]]:
    """Kapitoly zprávy podle Pokynu: (nadpis, odstavce). ``udaje``: projekt, body, kody, stanoviska, rozsah,
    vykres, datum_mereni, ku, obec, kraj, lokalita, ucel, zhotovitel, objednatel, pristroj, trida, testy."""
    g = lambda k, d=DOPLNTE: (str(udaje.get(k)).strip() or d) if udaje.get(k) not in (None, "") else d  # noqa: E731
    body = udaje.get("body") or 0
    kap = [
        ("Technická zpráva", [
            f"Akce: {g('lokalita', g('projekt'))}",
            f"Vyhotoveno: {dt.date.today():%d. %m. %Y}",
        ]),
        ("1. Základní údaje", [
            f"Datum měření: {g('datum_mereni')}",
            f"Kraj: {g('kraj')}, obec: {g('obec')}, katastrální území: {g('ku')}",
            f"Měřená lokalita: {g('lokalita', g('projekt'))}",
            f"Účel měření: {g('ucel', 'účelová mapa (cvičení z předmětu Mapování) ' + DOPLNTE)}",
            f"Zhotovitel: {g('zhotovitel')}",
            f"Objednatel: {g('objednatel')}",
            f"Úředně oprávněný zeměměřický inženýr, který výsledek ověřil: {g('uozi')}",
        ]),
        ("2. Souřadnicový a výškový systém", [
            "Polohový systém: S-JTSK (Křovákovo zobrazení), výškový systém: Balt po vyrovnání (Bpv).",
            f"Třída přesnosti mapování: {g('trida', '3')} (ČSN 01 3410).",
        ]),
        ("3. Přístrojové a jiné vybavení", [
            f"Totální stanice: {g('pristroj')}",
            f"GNSS aparatura: {g('gnss')}",
            "Software: Kontrola výkresu (výpočty, kontrola kresby), MicroStation " + DOPLNTE,
        ]),
        ("4. Využité podklady", [
            "Body bodového pole: geodetické údaje ČÚZK " + DOPLNTE,
            "Pokyn pro tvorbu účelové mapy (VUT FAST), ČSN 01 3410, ČSN 01 3411",
        ]),
        ("5. Měřické práce", [
            "Polohové a výškové připojení: " + DOPLNTE,
            "Pomocná měřická síť: " + DOPLNTE,
            "Podrobné měření: polární metoda" + (f" z {udaje['stanoviska']} stanovisek" if udaje.get("stanoviska")
                                                else "") + f", {DOPLNTE}",
        ]),
        ("6. Kancelářské práce", [
            f"Výpočet souřadnic a výšek: {body} bodů" + (f" ({udaje['rozsah']})" if udaje.get("rozsah") else "")
            + ".",
            "Kresba mapy: " + (f"výkres {udaje['vykres']}" if udaje.get("vykres") else DOPLNTE)
            + ", kontrola topologie a atributů aplikací Kontrola výkresu.",
            "Ověření přesnosti: " + (udaje.get("testy") or "Výpočty → Úlohy → Testování přesnosti ÚM " + DOPLNTE),
        ]),
        ("7. Seznam příloh", [
            "1. Seznam souřadnic a výšek (*.txt)",
            "2. Protokol o výpočtu (*.txt)",
            "3. Přehledný náčrt bodového pole a pomocné měřické sítě",
            "4. Účelová mapa (výkres *.dgn a tisk *.pdf)",
            "5. Fotodokumentace",
        ]),
        ("8. Fotodokumentace", [DOPLNTE]),
        ("", [f"V {g('misto', DOPLNTE)} dne {dt.date.today():%d. %m. %Y}", "Vypracoval: " + g("zhotovitel")]),
    ]
    return kap


def jako_text(kap: list[tuple[str, list[str]]]) -> str:
    out = []
    for nadpis, odst in kap:
        if nadpis:
            out += [nadpis.upper() if not nadpis[0].isdigit() else nadpis, ""]
        out += odst + [""]
    return "\n".join(out)


def _odstavec(text: str, nadpis: int = 0) -> str:
    vel = {0: 22, 1: 36, 2: 26}[nadpis]
    tucne = "<w:b/>" if nadpis else ""
    zvyrazni = '<w:highlight w:val="yellow"/>'
    casti = text.split(DOPLNTE)
    runs = []
    for i, c in enumerate(casti):
        if c:
            runs.append(f'<w:r><w:rPr>{tucne}<w:sz w:val="{vel}"/></w:rPr>'
                        f'<w:t xml:space="preserve">{escape(c)}</w:t></w:r>')
        if i < len(casti) - 1:  # místa k doplnění žlutě
            runs.append(f'<w:r><w:rPr>{tucne}<w:sz w:val="{vel}"/>{zvyrazni}</w:rPr>'
                        f'<w:t xml:space="preserve">{escape(DOPLNTE)}</w:t></w:r>')
    mezera = '<w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>' if nadpis else ""
    return f"<w:p>{mezera}{''.join(runs)}</w:p>"


def uloz_docx(path: str | Path, kap: list[tuple[str, list[str]]]) -> Path:
    """Minimální dokument Word (.docx) bez další knihovny: nadpisy tučně, místa k doplnění žlutě."""
    p = Path(path)
    telo = []
    for i, (nadpis, odst) in enumerate(kap):
        if nadpis:
            telo.append(_odstavec(nadpis, 1 if i == 0 else 2))
        telo += [_odstavec(t) for t in odst]
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(telo) +
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1418" w:right="1418" w:bottom="1418" '
           'w:left="1418" w:header="709" w:footer="709" w:gutter="0"/></w:sectPr></w:body></w:document>')
    typy = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", typy)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
    return p


def udaje_z_aplikace(win) -> dict:
    """Co o akci ví otevřená aplikace (projekt, seznam souřadnic, zápisník, výkres)."""
    u: dict = {}
    proj = getattr(win, "project", None)
    if proj is not None:
        u["projekt"] = getattr(proj, "name", "") or ""
    vyp = getattr(win, "vypocty", None)
    seznam = getattr(vyp, "seznam", None)
    if seznam is not None and len(seznam):
        u["body"] = len(seznam)
        cisla = [b.cislo for b in seznam.body]
        u["rozsah"] = f"čísla {cisla[0]} – {cisla[-1]}" if len(cisla) > 1 else f"bod {cisla[0]}"
    zap = getattr(vyp, "zapisnik", None)
    if zap is not None and getattr(zap, "stanoviska", None):
        u["stanoviska"] = len(zap.stanoviska)
    dr = getattr(win, "drawing", None)
    if dr is not None and getattr(dr, "path", None):
        u["vykres"] = Path(dr.path).name
    return u
