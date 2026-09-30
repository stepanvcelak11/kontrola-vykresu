"""Okno „Co aplikace umí“: přehled všech funkcí po skupinách, u každé tlačítko, které ji rovnou spustí."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

# (skupina, [(název, popis, akce v okně nebo None)])
FUNKCE = [
    ("Kontrola výkresu", [
        ("Kontrola topologie a atributů", "Nedotažení, přetažení, křížení bez uzlu, duplicity, krátké čáry, "
         "nezavřené plochy, prvky příliš blízko (Limit jako MGEO), vrstvy, barvy, styly, písmo podle Směrnice.",
         "a_check"),
        ("Kontrola ploch (MGEO)", "Z hranic sestaví plochy a hlídá, že každá má jeden popis / definiční bod "
         "a čísla se neopakují. Zapíná se v Nastavení kontrol.", "a_settings"),
        ("Hlídat změny výkresu", "Po uložení v MicroStationu se výkres sám znovu zkontroluje – i přímo DGN "
         "(Ctrl+S v MicroStationu), bez ukládání do DXF.", "a_watch"),
        ("Co zkontrolovat", "Zaškrtnete, co se má na výkrese kontrolovat, nebo zvolíte hotovou sadu (jako "
         "učitel, vše, jen topologie, vzhled mapy, cizí výkres bez pravidel). Nabídka je i u šipky tlačítka "
         "Zkontrolovat.", "a_vyber"),
        ("Obecná kontrola geometrie", "Na jakýkoli výkres: zbytečné lomové body, špičky (čára se vrací), "
         "nepatrné a úzké plochy, překryv čar, nečitelně malý text.", "a_vyber"),
        ("Kartografická kontrola", "Popisy přes sebe, popis přeškrtnutý čarou, číslo bodu daleko od bodu, "
         "popis vzhůru nohama – to, co učitel vidí okem na mapě.", "a_check"),
        ("Otevřít DGN přímo", "Výkres z MicroStationu V8i / CONNECT se čte přímo z DGN (experimentálně): "
         "vrstvy, přesné barvy, tloušťky a styly, texty, buňky, oblouky.", "a_open"),
        ("Připraveno k odevzdání?", "Souhrn: co ještě chybí, skóre a co opravit jako první.", "a_ready"),
        ("Hromadná kontrola", "Celá složka výkresů najednou s přehledovou tabulkou.", "a_batch"),
    ]),
    ("Opravy", [
        ("Automatická oprava", "Do nového souboru: smaže duplicity a nulové délky, dotáhne a zkrátí čáry, vloží "
         "uzly, rozdělí čáry v uzlu, uzavře plochy, odstraní zbytečné lomové body, přichytí body těsně u čáry, "
         "smaže zdvojené body, přesune prvky na správnou vrstvu. Originál zůstane beze změny.", "a_repair"),
        ("Opravný průvodce (MicroStation)", "Chyby jedna po druhé, seřazené podle polohy: přesně odkud kam "
         "posunout vrchol, o kolik, souřadnice cíle a key-in ke zkopírování. Opravujete sami v DGN; "
         "opravný list jde i vytisknout.", "a_fixguide"),
        ("Návod ke každé chybě", "U chyby postup v MicroStationu krok za krokem s obrázkem.", None),
        ("Chyby přímo v MicroStationu", "Makro pro MicroStation ukáže chyby jako dočasné kroužky (do DGN se "
         "neukládají), F8 skočí na další chybu.", "a_ms_help"),
        ("Rychlé tipy – MicroStation", "Rovnoběžka, kolmice, prodloužení, AccuDraw, přichycení…", "_tips"),
    ]),
    ("Body a souřadnice", [
        ("Ověřit seznam souřadnic", "Sedí body ve výkresu na seznam? Chybějící, posunuté, špatné číslo nebo "
         "výška, body navíc – tabulka a přiblížení.", "a_seznam"),
        ("Spojnice podle náčrtu", "Zapíšete, co je v náčrtu spojené (např. plot 1-2-3-4), a aplikace ověří, "
         "že to ve výkresu máte nakreslené na správné vrstvě.", "a_spojnice"),
        ("Výpočet ze zápisníku", "Polární metoda a kontrola výpočtu z Gromy s diagnózou rozdílů.",
         "a_vypocet"),
    ]),
    ("Zadání a pravidla", [
        ("Směrnice / zadání → pravidla", "Z Excelu, Wordu nebo PDF od učitele vzniknou pravidla kontroly "
         "(vrstvy, barvy, tloušťky, písmo).", "_zadani"),
        ("Pokyny ze Wordu / PDF", "Požadavky („musí / nesmí“), měřítko, písmo, tolerance – s tlačítkem "
         "„Použít v nastavení“.", "_dokumenty"),
        ("Porovnat s PDF od učitele", "Vektorové PDF z MicroStationu se samo umístí na výkres podle popisů a "
         "ukáže čáry, které vám chybí nebo přebývají (Zadání → Vzor → Porovnat).", "_vzor"),
        ("Náčrt vedle výkresu", "Fotka náčrtu nebo PDF vzor vedle kresby, i s georeferencí.", "a_sketch"),
    ]),
    ("Porovnání a protokoly", [
        ("Časová osa výkresu", "Každá zkontrolovaná verze se uloží: přehrát vznik výkresu, kde přibyly "
         "chyby, porovnat s dneškem, vytáhnout omylem smazané prvky.", "a_timeline"),
        ("Učitelův pohled", "Předpověď protokolu od učitele – aplikace se učí z jeho dřívějších protokolů – "
         "a náhled protokolu v jeho formátu.", "a_predikce"),
        ("Náhled tisku v měřítku", "Mapa do PDF přesně v měřítku 1:500 / 1:1000 s tloušťkami čar jako na "
         "tisku.", "a_print_preview"),
        ("Porovnat verze výkresu", "Co se změnilo mezi dvěma verzemi (přidáno, smazáno, posunuto).", "a_compare"),
        ("Porovnat s protokolem učitele", "Načte .log z MGEO / GISoft a ukáže, co učitel hlásil a jak na tom "
         "jste teď.", "a_teacher"),
        ("Protokoly", "PDF, Excel, CSV, interaktivní HTML, seznam k opravě na tisk, DXF s vrstvou chyb, "
         "protokol ve formátu MGEO (.log).", "a_exp_html"),
    ]),
    ("Pomocníci", [
        ("Poradce", "Zeptejte se česky: „co dál“, „kolik mi zbývá“, „jak opravit tuhle chybu“ – zná váš "
         "projekt, pravidla i pokyny ze zadání. Funguje offline.", "_poradce"),
        ("Průvodce", "Krok za krokem od zadání k odevzdání.", "_guide"),
        ("Klávesové zkratky", "Přehled všech zkratek.", "_shortcuts"),
    ]),
]


class FeaturesDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Co aplikace umí")
        self.resize(900, 680)
        lay = QVBoxLayout(self)
        head = QLabel("<h2 style='margin:0'>Co aplikace umí</h2>Tlačítkem funkci rovnou spustíte.")
        lay.addWidget(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat funkci (např. body, oprava, Word)…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self.grid = QVBoxLayout(body)
        self.cards: list[tuple[QWidget, str]] = []
        self.groups: list[tuple[QLabel, list[QWidget]]] = []
        for group, items in FUNKCE:
            gl = QLabel(f"<b>{group}</b>")
            gl.setStyleSheet("font-size: 11pt; margin-top: 8px;")
            self.grid.addWidget(gl)
            g = QGridLayout()
            members = []
            for i, (name, desc, act) in enumerate(items):
                card = self._card(name, desc, act)
                g.addWidget(card, i // 2, i % 2)
                members.append(card)
                self.cards.append((card, f"{group} {name} {desc}".lower()))
            self.grid.addLayout(g)
            self.groups.append((gl, members))
        self.grid.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _card(self, name: str, desc: str, act: str | None) -> QWidget:
        fr = QFrame()
        fr.setObjectName("karta")
        fl = QVBoxLayout(fr)
        fl.setContentsMargins(12, 8, 12, 8)
        a = getattr(self.win, act, None) if act and act.startswith("a_") else None
        sc = a.shortcut().toString(QKeySequence.NativeText) if a is not None else ""
        t = QLabel(f"<b>{name}</b>" + (f" <span style='color:#6B7280'>({sc})</span>" if sc else ""))
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setObjectName("karta_popis")
        fl.addWidget(t)
        fl.addWidget(d)
        if act:
            b = QPushButton("Spustit")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, x=act: self._run(x))
            r = QHBoxLayout()
            r.addStretch(1)
            r.addWidget(b)
            fl.addLayout(r)
        return fr

    def _run(self, act: str):
        w = self.win
        self.accept()
        special = {
            "_tips": w.show_tips, "_guide": w.show_guide, "_shortcuts": w.show_shortcuts,
            "_poradce": lambda: (w.poradce_dock.show(), w.poradce_dock.raise_()),
            "_zadani": lambda: w.tabs.setCurrentWidget(w.zadani),
            "_vzor": lambda: (w.tabs.setCurrentWidget(w.zadani),
                              w.zadani.tabs.setCurrentWidget(w.zadani.template_page)),
            "_dokumenty": lambda: (w.tabs.setCurrentWidget(w.zadani),
                                   w.zadani.tabs.setCurrentWidget(w.zadani.documents_page)),
        }
        if act in special:
            special[act]()
            return
        a = getattr(w, act, None)
        if a is not None:
            if a.isCheckable():
                a.setChecked(True)
            else:
                a.trigger()

    def _filter(self, text: str):
        q = text.strip().lower()
        for card, key in self.cards:
            card.setVisible(not q or all(w in key for w in q.split()))
        for gl, members in self.groups:
            gl.setVisible(any(not m.isHidden() for m in members))
