"""Vytvoří ukázková data pro vyzkoušení aplikace.

* ``ukazkovy_vykres.dxf`` – malý polohopis v S-JTSK s úmyslnými chybami,
* ``vzorovy_vykres.dxf`` – „vzor od učitele“ se správnými hladinami a styly,
* ``tabulka_atributu.xlsx`` a ``tabulka_atributu.csv`` – číselník prvků,
* ``nacrt.png`` – jednoduchý náčrt.

Spuštění:  python ukazky/vytvor_ukazky.py
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import ezdxf
import ezdxf.colors

HERE = Path(__file__).resolve().parent
X0, Y0 = -743200.0, -1043500.0  # levý dolní roh v S-JTSK (souřadnice DXF z MicroStationu)

TABULKA = [
    # kód, název, hladina, barva (číslo MicroStationu), styl, typ, povinné atributy, povolené hodnoty,
    # blok, text na hladině
    ("101", "Budova", "BUDOVY", "3 (červená)", "plná", "plocha", "", "", "", "POPIS_BUDOV"),
    ("102", "Parcela", "PARCELY", "2 (zelená)", "plná", "plocha", "", "", "", "PARCELNI_CISLA"),
    ("201", "Okraj silnice", "KOMUNIKACE", "8", "plná", "linie", "", "", "", ""),
    ("202", "Okraj chodníku", "KOMUNIKACE", "9", "čárkovaná", "linie", "", "", "", ""),
    ("301", "Plot", "PLOTY", "1 (modrá)", "DASHDOT", "linie", "", "", "", ""),
    ("401", "Podrobný bod", "BODY", "0", "", "bod", "CISLO, KOD", "", "BOD", ""),
    ("402", "Strom listnatý", "VEGETACE", "2", "", "bod", "DRUH", "lípa, dub, javor, bříza, buk", "STROM_L", ""),
    ("403", "Šachta", "SITE", "5", "", "bod", "", "", "SACHTA", ""),
    ("501", "Popis budovy (č. p.)", "POPIS_BUDOV", "0", "", "text", "", "", "", ""),
    ("502", "Parcelní číslo", "PARCELNI_CISLA", "2", "", "text", "", "", "", ""),
    ("???", "Lavička", "MOBILIAR", "", "", "", "", "", "", ""),  # záměrně neúplný řádek
]


def _layers(doc):
    for name, color, lt in [("BUDOVY", 1, "CONTINUOUS"), ("PARCELY", 3, "CONTINUOUS"),
                            ("KOMUNIKACE", 8, "CONTINUOUS"), ("PLOTY", 5, "DASHDOT"),
                            ("BODY", 7, "CONTINUOUS"), ("VEGETACE", 3, "CONTINUOUS"),
                            ("SITE", 6, "CONTINUOUS"), ("POPIS_BUDOV", 7, "CONTINUOUS"),
                            ("PARCELNI_CISLA", 3, "CONTINUOUS"), ("RAM", 7, "CONTINUOUS")]:
        doc.layers.add(name, color=color, linetype=lt)


def _blocks(doc):
    b = doc.blocks.new("BOD")
    b.add_circle((0, 0), 0.25)
    b.add_attdef("CISLO", (0.4, 0.1), dxfattribs={"height": 0.8})
    b.add_attdef("KOD", (0.4, -0.9), dxfattribs={"height": 0.5, "flags": 1})
    s = doc.blocks.new("STROM_L")
    s.add_circle((0, 0), 1.2)
    s.add_line((-0.3, 0), (0.3, 0))
    s.add_line((0, -0.3), (0, 0.3))
    s.add_attdef("DRUH", (1.4, 0), dxfattribs={"height": 0.6, "flags": 1})
    sa = doc.blocks.new("SACHTA")
    sa.add_lwpolyline([(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)], close=True)
    sa.add_line((-0.5, -0.5), (0.5, 0.5))


def P(x, y):
    return (X0 + x, Y0 + y)


def _new_doc():
    doc = ezdxf.new("R2013", setup=True)
    doc.header["$INSUNITS"] = 6
    _layers(doc)
    _blocks(doc)
    return doc


def _insert(msp, name, xy, layer, attribs=None):
    ins = msp.add_blockref(name, P(*xy), dxfattribs={"layer": layer})
    if attribs:
        ins.add_auto_attribs(attribs)
    return ins


def vytvor_vykres(path: Path, s_chybami: bool = True):
    doc = _new_doc()
    msp = doc.modelspace()
    bl = {"layer": "BUDOVY"}
    # --- parcely (sdílené hranice)
    parcels = [
        [(0, 0), (60, 0), (60, 50), (0, 50)],
        [(60, 0), (120, 0), (120, 50), (60, 50)],
        [(0, 50), (60, 50), (60, 100), (0, 100)],
    ]
    if s_chybami:
        # čtvrtá parcela překrývá druhou (1 m) a mezi třetí a čtvrtou je štěrbina 2 cm
        parcels.append([(59.0, 50.02), (120, 50.02), (120, 100), (59.0, 100)])
    else:
        parcels.append([(60, 50), (120, 50), (120, 100), (60, 100)])
    for pts in parcels:
        msp.add_lwpolyline([P(*p) for p in pts], close=True, dxfattribs={"layer": "PARCELY"})
    for txt, xy in [("125/1", (30, 25)), ("125/2", (90, 25)), ("126", (30, 75)), ("127", (90, 75))]:
        msp.add_text(txt, height=1.5, dxfattribs={"layer": "PARCELNI_CISLA"}).set_placement(P(*xy))
    # --- budovy
    msp.add_lwpolyline([P(10, 10), P(30, 10), P(30, 25), P(10, 25)], close=True, dxfattribs=bl)
    msp.add_text("č.p. 12", height=1.2, dxfattribs={"layer": "POPIS_BUDOV"}).set_placement(P(15, 17))
    if s_chybami:
        # nezavřená budova – mezera 3 cm
        msp.add_lwpolyline([P(70, 10), P(90, 10), P(90, 30), P(70, 30), P(70, 10.03)], dxfattribs=bl)
        msp.add_text("č.p. 13", height=1.2, dxfattribs={"layer": "POPIS_BUDOV"}).set_placement(P(75, 20))
        # budova bez popisu
        msp.add_lwpolyline([P(10, 60), P(25, 60), P(25, 75), P(10, 75)], close=True, dxfattribs=bl)
        # popis mimo budovu
        msp.add_text("č.p. 99", height=1.2, dxfattribs={"layer": "POPIS_BUDOV"}).set_placement(P(40, 90))
        # samoprotínající se budova („motýlek“)
        msp.add_lwpolyline([P(80, 60), P(100, 80), P(100, 60), P(80, 80)], close=True, dxfattribs=bl)
        msp.add_text("č.p. 15", height=1.2, dxfattribs={"layer": "POPIS_BUDOV"}).set_placement(P(95, 70))
        # budova nakreslená jinou barvou (zelená místo červené)
        msp.add_lwpolyline([P(35, 60), P(50, 60), P(50, 72), P(35, 72)], close=True,
                           dxfattribs={"layer": "BUDOVY", "color": 3})
        msp.add_text("č.p. 14", height=1.2, dxfattribs={"layer": "POPIS_BUDOV"}).set_placement(P(40, 65))
    else:
        msp.add_lwpolyline([P(70, 10), P(90, 10), P(90, 30), P(70, 30)], close=True, dxfattribs=bl)
        msp.add_text("č.p. 13", height=1.2, dxfattribs={"layer": "POPIS_BUDOV"}).set_placement(P(75, 20))
    # --- komunikace
    kom = {"layer": "KOMUNIKACE"}
    msp.add_line(P(0, -5), P(120, -5), dxfattribs={**kom, "color": 8, "true_color": 0x404040})
    msp.add_line(P(0, -12), P(120, -12), dxfattribs={**kom, "color": 8, "true_color": 0x404040})
    # MicroStation ukládá barvy do DXF i jako RGB (true color) – barva 9 = světle šedá
    msp.add_line(P(0, -3), P(120, -3), dxfattribs={**kom, "color": 9, "linetype": "DASHED",
                                                   "true_color": ezdxf.colors.rgb2int((192, 192, 192))})
    if s_chybami:
        # příčná silnice kříží okraje bez uzlu
        msp.add_line(P(50, -20), P(50, -1), dxfattribs={**kom, "color": 8, "true_color": 0x404040})
        # duplicitní okraj
        msp.add_line(P(0, -12), P(120, -12), dxfattribs={**kom, "color": 8, "true_color": 0x404040})
        # linie nulové délky
        msp.add_line(P(10, -8), P(10, -8), dxfattribs={**kom, "color": 8, "true_color": 0x404040})
    # --- plot se zapojením na budovu
    pl = {"layer": "PLOTY"}
    msp.add_lwpolyline([P(30, 25), P(30, 40), P(55, 40)], dxfattribs=pl)
    if s_chybami:
        msp.add_lwpolyline([P(90, 30), P(90, 45), P(110, 45)], dxfattribs=pl)
        # plot nedotažený k budově o 3 cm a o 4 cm
        msp.add_lwpolyline([P(110, 45), P(110, 20), P(90.03, 20)], dxfattribs=pl)
        msp.add_lwpolyline([P(10, 25.04), P(10, 45)], dxfattribs=pl)
        # plot na nepovolené hladině
        msp.add_line(P(0, 47), P(20, 47), dxfattribs={"layer": "POKUS"})
        # budova nakreslená jako otevřená linie na hladině plotů – nekódovaný typ
        msp.add_circle(P(115, 90), 0.5, dxfattribs={"layer": "BUDOVY"})
    # --- body
    body = [((0, 0), "1001"), ((60, 0), "1002"), ((120, 0), "1003"), ((60, 50), "1004"),
            ((0, 100), "1006"), ((120, 100), "1007")]
    for xy, c in body:
        _insert(msp, "BOD", xy, "BODY", {"CISLO": c, "KOD": "401"})
    _insert(msp, "STROM_L", (45, 30), "VEGETACE", {"DRUH": "lípa"})
    _insert(msp, "STROM_L", (48, 85), "VEGETACE", {"DRUH": "dub"})
    _insert(msp, "SACHTA", (100, -8), "SITE")
    if s_chybami:
        _insert(msp, "BOD", (120.004, 50.0), "BODY", {"CISLO": "1005", "KOD": "401"})
        _insert(msp, "BOD", (120.0, 50.0), "BODY", {"CISLO": "1015", "KOD": "401"})  # 4 mm od předchozího
        _insert(msp, "BOD", (0, 50), "BODY", {"CISLO": "", "KOD": "401"})  # chybí číslo
        _insert(msp, "STROM_L", (52, 20), "VEGETACE", {"DRUH": "smrk"})  # nepovolená hodnota
        _insert(msp, "STROM_L", (5, 88), "VEGETACE")  # chybí druh
        _insert(msp, "BOD", (260, 180), "BODY", {"CISLO": "9999", "KOD": "401"})  # mimo rozsah
        msp.add_point(P(70, 90), dxfattribs={"layer": "BODY"})  # bod bez kódu
        msp.add_point(P(70, 90), dxfattribs={"layer": "BODY"})  # duplicitní bod
    doc.saveas(path)


def vytvor_tabulku():
    header = ["Kód", "Název prvku", "Hladina (level)", "Barva", "Styl čáry", "Typ geometrie",
              "Povinné atributy", "Povolené hodnoty", "Buňka", "Popis na hladině"]
    with open(HERE / "tabulka_atributu.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(header)
        w.writerows(TABULKA)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "Číselník"
    ws.append(["Tabulka prvků – cvičení z mapování (ukázka)"])
    ws.append([])
    ws.append(header)
    for c in ws[3]:
        c.font = Font(bold=True)
    for row in TABULKA:
        ws.append(list(row))
    for col, w in zip("ABCDEFGHIJ", (6, 22, 16, 12, 12, 14, 18, 30, 10, 18)):
        ws.column_dimensions[col].width = w
    wb.save(HERE / "tabulka_atributu.xlsx")


def vytvor_nacrt():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    img = Image.new("RGB", (900, 700), (250, 248, 240))
    d = ImageDraw.Draw(img)
    s = 6.0

    def t(x, y):
        return (60 + x * s, 640 - y * s)

    for pts in ([(0, 0), (60, 0), (60, 50), (0, 50)], [(60, 0), (120, 0), (120, 50), (60, 50)],
                [(0, 50), (60, 50), (60, 100), (0, 100)], [(60, 50), (120, 50), (120, 100), (60, 100)]):
        d.polygon([t(*p) for p in pts], outline=(40, 120, 40))
    for pts in ([(10, 10), (30, 10), (30, 25), (10, 25)], [(70, 10), (90, 10), (90, 30), (70, 30)]):
        d.polygon([t(*p) for p in pts], outline=(200, 30, 30), width=3)
    d.text(t(15, 18), "c.p. 12", fill=(0, 0, 0))
    d.text(t(75, 20), "c.p. 13", fill=(0, 0, 0))
    d.line([t(30, 25), t(30, 40), t(55, 40)], fill=(30, 30, 200), width=2)
    for xy in ((45, 30), (48, 85)):
        x, y = t(*xy)
        d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(30, 140, 30), width=2)
    d.text((20, 15), "Nacrt – cviceni z mapovani (ukazka)", fill=(0, 0, 0))
    img.save(HERE / "nacrt.png")


if __name__ == "__main__":
    vytvor_vykres(HERE / "ukazkovy_vykres.dxf", s_chybami=True)
    vytvor_vykres(HERE / "vzorovy_vykres.dxf", s_chybami=False)
    vytvor_tabulku()
    vytvor_nacrt()
    print("Ukázková data vytvořena ve složce", HERE)
