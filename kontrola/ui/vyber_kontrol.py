"""Okno „Co zkontrolovat“: všechny kontroly po skupinách k zaškrtnutí + hotové výběry (jako učitel, vše…)."""

from __future__ import annotations

from PySide6.QtCore import Qt
import re
from collections import Counter

from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ..checks.base import REGISTRY

SKUPINY = [
    ("Topologie", "Topologie čar a ploch", "Napojení, křížení, duplicity, překryvy – jako kontrola kresby MGEO."),
    ("Atributy", "Atributy podle pravidel", "Vrstva, barva, styl, tloušťka, písmo – jako kontrola symbologie GISoft. "
                                            "Většina potřebuje pravidla ze Směrnice."),
    ("Geometrie", "Geometrie", "Zbytečné lomové body, špičky, nepatrné plochy – na jakýkoli výkres."),
    ("Kartografie", "Kartografie a vzhled mapy", "Popisy přes sebe, přes čáry, čísla bodů, čitelnost textu."),
]

# kontroly, které dělá učitelův MGEO (kontrola kresby) a GISoft (kontrola symbologie)
UCITEL = {"chybejici_napojeni", "visici_konce", "duplicity", "prekryv_linii", "pruseciky_bez_uzlu", "nulova_delka",
          "kratke_linie", "blizke_prvky", "samoprotnuti", "nezavrene_polygony", "body_blizko", "symbologie",
          "typ_geometrie", "atribut_dle_vrstvy", "nepovolene_hladiny", "nekodovane", "texty", "atributy",
          "seznam_souradnic"}

PRESETY = [
    ("Jako učitel", "MGEO + GISoft – co uvidí v protokolu", lambda cid, cls: cid in UCITEL),
    ("Vše, co jde", "Všechny kontroly", lambda cid, cls: True),
    ("Jen topologie", "Napojení, křížení, duplicity…", lambda cid, cls: cls.skupina == "Topologie"),
    ("Jen atributy", "Vrstvy, barvy, styly, písmo", lambda cid, cls: cls.skupina == "Atributy"),
    ("Vzhled mapy", "Kartografie + geometrie", lambda cid, cls: cls.skupina in ("Kartografie", "Geometrie")),
    ("Cizí výkres (bez pravidel)", "Vše, co nepotřebuje Směrnici",
     lambda cid, cls: not getattr(cls, "potrebuje_pravidla", False)),
]


def _first_sentence(text: str, limit: int = 120) -> str:
    """První věta popisu (tečka za zkratkou jako „např.“ větu nekončí), zkrácená na ``limit`` znaků."""
    m = re.search(r"(?<!např)(?<!tzv)(?<!č)\.\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])", text)
    first = text[:m.start() + 1] if m else text
    return first if len(first) <= limit else first[:limit].rsplit(" ", 1)[0] + "…"


class VyberKontrol(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.cfg = win.project.config
        self.run_now = False
        self.setWindowTitle("Co zkontrolovat")
        self.resize(860, 700)
        lay = QVBoxLayout(self)
        head = QLabel("<h2 style='margin:0'>Co zkontrolovat</h2>Zaškrtněte, co chcete teď na výkrese kontrolovat, "
                      "nebo vyberte hotovou sadu. Výběr se uloží do projektu.")
        head.setWordWrap(True)
        lay.addWidget(head)
        prow = QHBoxLayout()
        prow.setSpacing(6)
        for name, tip, pred in PRESETY:
            b = QPushButton(name)
            b.setObjectName("rychly_filtr")
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, p=pred: self.apply_preset(p))
            prow.addWidget(b)
        prow.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat kontrolu…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(220)
        self.search.textChanged.connect(self._filter)
        prow.addWidget(self.search)
        lay.addLayout(prow)
        found = Counter(i.check_id for i in (getattr(win, "issues", None) or []))
        self.rows: dict[str, list[QWidget]] = {}
        self.cards: dict[str, QFrame] = {}
        has_rules = bool(win.project.rules.pravidla)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        bl = QVBoxLayout(body)
        self.boxes: dict[str, QCheckBox] = {}
        self.group_boxes: dict[str, QCheckBox] = {}
        for key, title, desc in SKUPINY:
            ids = [cid for cid, cls in REGISTRY.items() if cls.skupina == key]
            if not ids:
                continue
            card = QFrame()
            card.setObjectName("karta")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            gh = QHBoxLayout()
            g = QCheckBox(title)
            g.setStyleSheet("font-weight: 800; font-size: 10.5pt;")
            g.setTristate(False)
            g.clicked.connect(lambda on, k=key: self._set_group(k, on))
            self.group_boxes[key] = g
            gh.addWidget(g)
            d = QLabel(desc)
            d.setObjectName("karta_popis")
            d.setWordWrap(True)
            gh.addWidget(d, 1)
            cl.addLayout(gh)
            for cid in ids:
                cls = REGISTRY[cid]
                row = QHBoxLayout()
                row.setContentsMargins(22, 0, 0, 0)
                cb = QCheckBox(cls.nazev)
                cb.setChecked(self.cfg.settings(cid).zapnuto)
                cb.setToolTip(cls.popis)
                cb.toggled.connect(lambda _on, k=key: self._sync_group(k))
                self.boxes[cid] = cb
                row.addWidget(cb)
                note = _first_sentence(cls.popis)
                if getattr(cls, "potrebuje_pravidla", False) and not has_rules:
                    note = "⚠ potřebuje pravidla (Směrnici) – zatím nejsou načtena. " + note
                nl = QLabel(note)
                nl.setObjectName("karta_popis")
                nl.setWordWrap(True)
                row.addWidget(nl, 1)
                widgets = [cb, nl]
                if found.get(cid):
                    badge = QLabel(f"minule {found[cid]}×")
                    badge.setToolTip("Počet míst, která kontrola našla při posledním spuštění")
                    badge.setStyleSheet("color:#B45309; font-weight:600;")
                    badge.setMinimumWidth(badge.sizeHint().width())
                    row.addWidget(badge)
                    widgets.append(badge)
                self.rows[cid] = widgets
                cl.addLayout(row)
            self.cards[key] = card
            bl.addWidget(card)
            self._sync_group(key)
        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        self.count = QLabel()
        brow = QHBoxLayout()
        brow.addWidget(self.count)
        brow.addStretch(1)
        b_save = QPushButton("Uložit výběr")
        b_save.clicked.connect(self.save)
        b_run = QPushButton("Zkontrolovat vybrané (F5)")
        b_run.setProperty("primarni", True)
        b_run.setDefault(True)
        b_run.clicked.connect(self.save_and_run)
        b_cancel = QPushButton("Zrušit")
        b_cancel.clicked.connect(self.reject)
        for b in (b_save, b_run, b_cancel):
            brow.addWidget(b)
        lay.addLayout(brow)
        for cb in self.boxes.values():
            cb.toggled.connect(self._update_count)
        self._update_count()

    def _filter(self, text: str):
        t = text.strip().lower()
        for key, card in self.cards.items():
            any_visible = False
            for cid, widgets in self.rows.items():
                cls = REGISTRY[cid]
                if cls.skupina != key:
                    continue
                vis = not t or t in cls.nazev.lower() or t in cls.popis.lower() or t in cid
                for w in widgets:
                    w.setVisible(vis)
                any_visible |= vis
            card.setVisible(any_visible)

    def _set_group(self, key: str, on: bool):
        for cid, cb in self.boxes.items():
            if REGISTRY[cid].skupina == key:
                cb.setChecked(on)

    def _sync_group(self, key: str):
        g = self.group_boxes.get(key)
        if g is None:
            return
        members = [cb for cid, cb in self.boxes.items() if REGISTRY[cid].skupina == key]
        g.blockSignals(True)
        g.setChecked(bool(members) and all(cb.isChecked() for cb in members))
        g.blockSignals(False)

    def _update_count(self, *_):
        n = sum(cb.isChecked() for cb in self.boxes.values())
        self.count.setText(f"Vybráno {n} z {len(self.boxes)} kontrol")

    def apply_preset(self, pred):
        for cid, cb in self.boxes.items():
            cb.setChecked(bool(pred(cid, REGISTRY[cid])))

    def save(self):
        for cid, cb in self.boxes.items():
            self.cfg.settings(cid).zapnuto = cb.isChecked()
        self.win.project.save()
        self.accept()

    def save_and_run(self):
        self.run_now = True
        self.save()


def apply_preset_to(config, name: str) -> None:
    """Nastaví zapnuté kontroly podle hotové sady (pro rychlé menu u tlačítka Zkontrolovat)."""
    pred = next(p for n, _t, p in PRESETY if n == name)
    for cid, cls in REGISTRY.items():
        config.settings(cid).zapnuto = bool(pred(cid, cls))
