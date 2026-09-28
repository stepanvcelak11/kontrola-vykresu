"""Průvodce: krok za krokem od zadání k odevzdání (zobrazí se při prvním spuštění, pak v menu Nápověda)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

# (nadpis, text, [(tlačítko, akce v hlavním okně)])
STEPS = [
    ("Vítejte v Kontrole výkresu",
     "Program zkontroluje váš výkres z MicroStationu <b>stejně jako učitel</b> – topologii (napojení čar, "
     "křížení, duplicity; obdoba MGEO) i atributy (vrstva, barva, styl, písmo; obdoba GISoft) – ještě "
     "<b>před odevzdáním</b>.<br><br>Program výkres <b>neopravuje</b>: ukáže, kde je chyba a jak ji "
     "v MicroStationu opravit. Všechna data zůstávají jen na vašem počítači.<br><br>"
     "Průvodce má 5 krátkých kroků.", []),
    ("1. Uložte výkres jako DXF",
     "V MicroStationu: <b>Soubor → Uložit jako</b>, typ souboru <b>AutoCAD (*.dxf)</b>. "
     "DGN soubor přímo číst neumíme, DXF obsahuje vše potřebné (vrstvy, barvy, styly, buňky).<br><br>"
     "Po každé úpravě stačí DXF uložit znovu – program si změny sám všimne a zkontroluje výkres znovu.",
     [("Podrobný návod k převodu", "dgn_help")]),
    ("2. Nahrajte zadání od učitele",
     "V záložce <b>Zadání</b> přetáhněte soubory od učitele: Směrnici (Word, PDF nebo Excel s tabulkou "
     "vrstev, barev a stylů), seznam souřadnic, náčrt. Z tabulky se vytvoří <b>pravidla</b>, podle kterých "
     "se kontrolují atributy.<br><br>Pokud nahrajete špatný soubor, jde ho v záložce Zadání odebrat.<br><br>"
     "{pravidla}",
     [("Otevřít záložku Zadání", "zadani")]),
    ("3. Otevřete výkres a zkontrolujte",
     "Tlačítko <b>Otevřít</b> (nebo přetáhnout DXF do okna), pak <b>Zkontrolovat</b> (F5).<br><br>"
     "Kreslíte teprve? Zapněte <b>Rozpracovaný výkres</b> – program pak nehlásí chyby jen proto, že ještě "
     "něco nemáte nakreslené. <b>Jen tento výřez</b> omezí seznam na část, kterou vidíte.<br><br>{vykres}",
     [("Otevřít výkres…", "open")]),
    ("4. Procházejte a opravujte chyby",
     "Klikněte na řádek chyby – výkres se přiblíží na místo a pod seznamem uvidíte <b>jak chybu opravit</b>. "
     "Tlačítko <b>Najít v MicroStationu</b> zkopíruje příkaz, který v MicroStationu vycentruje pohled na "
     "místo chyby.<br><br>Nevíte, co chyba znamená? Tlačítko <b>? Co to znamená</b> ukáže vysvětlení "
     "s obrázkem.<br><br>Opravenou chybu označte <b>✓ Opraveno</b> (Ctrl+Enter), záměr <b>✕ Ignorovat</b>. "
     "Kliknutím na prvek ve výkresu uvidíte v panelu <b>Prvek</b> jeho vlastnosti a co říká Směrnice.",
     [("Vysvětlení chyb a pojmů", "help")]),
    ("5. Před odevzdáním",
     "Tlačítko <b>Připraveno k odevzdání?</b> spustí úplnou kontrolu s tolerancemi učitele a ukáže semafor: "
     "zelená = můžete odevzdat. Hlídá i počet odevzdání a průběh počtu chyb v čase.<br><br>"
     "Protokol od učitele (.log) můžete načíst přes <b>Kontrola → Porovnat s protokolem učitele</b>.<br><br>"
     "Hodně štěstí!", [("Připraveno k odevzdání?", "ready")]),
]


class GuideDialog(QDialog):
    def __init__(self, win, parent=None):
        super().__init__(parent or win)
        self.win = win
        self.setWindowTitle("Průvodce")
        self.resize(620, 430)
        lay = QVBoxLayout(self)
        self.dots = QLabel()
        self.dots.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.dots)
        self.stack = QStackedWidget()
        self.texts: list[QLabel] = []
        for title, text, actions in STEPS:
            w = QWidget()
            wl = QVBoxLayout(w)
            h = QLabel(f"<h2>{title}</h2>")
            wl.addWidget(h)
            t = QLabel()
            t.setWordWrap(True)
            t.setTextFormat(Qt.RichText)
            t.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            t.setStyleSheet("font-size: 11pt;")
            wl.addWidget(t, 1)
            self.texts.append(t)
            ar = QHBoxLayout()
            for label, key in actions:
                b = QPushButton(label)
                b.clicked.connect(lambda _c=False, k=key: self._action(k))
                ar.addWidget(b)
            ar.addStretch(1)
            wl.addLayout(ar)
            self.stack.addWidget(w)
        lay.addWidget(self.stack, 1)
        bottom = QHBoxLayout()
        self.cb_hide = QCheckBox("Při spuštění už nezobrazovat")
        self.cb_hide.setChecked(True)
        bottom.addWidget(self.cb_hide)
        bottom.addStretch(1)
        self.b_back = QPushButton("◀ Zpět")
        self.b_back.clicked.connect(lambda: self.go(-1))
        self.b_next = QPushButton("Další ▶")
        self.b_next.setDefault(True)
        self.b_next.clicked.connect(lambda: self.go(1))
        bottom.addWidget(self.b_back)
        bottom.addWidget(self.b_next)
        lay.addLayout(bottom)
        self.go(0)

    def _status(self) -> dict[str, str]:
        win = self.win
        n = len(win.project.rules.pravidla) if getattr(win, "project", None) is not None else 0
        pravidla = (f"<span style='color:#16A34A'>✓ V projektu je {n} pravidel.</span>" if n else
                    "<span style='color:#B45309'>Zatím nemáte žádná pravidla – bez nich se kontroluje jen "
                    "topologie.</span>")
        d = getattr(win, "drawing", None)
        if d is not None:
            from pathlib import Path
            vykres = (f"<span style='color:#16A34A'>✓ Otevřený výkres: "
                      f"{Path(d.source_path or d.path).name}</span>")
        else:
            vykres = "<span style='color:#B45309'>Zatím není otevřený žádný výkres.</span>"
        return {"pravidla": pravidla, "vykres": vykres}

    def go(self, delta: int):
        i = self.stack.currentIndex() + delta
        if i >= len(STEPS):
            self.accept()
            return
        i = max(0, i)
        st = self._status()
        for k, (_, text, _a) in enumerate(STEPS):
            self.texts[k].setText(text.format(**st))
        self.stack.setCurrentIndex(i)
        self.b_back.setEnabled(i > 0)
        self.b_next.setText("Hotovo" if i == len(STEPS) - 1 else "Další ▶")
        self.dots.setText("  ".join("●" if k == i else "○" for k in range(len(STEPS))))

    def _action(self, key: str):
        win = self.win
        if key == "dgn_help":
            win._dgn_help()
        elif key == "zadani":
            win.tabs.setCurrentWidget(win.zadani)
        elif key == "open":
            win.open_dialog()
        elif key == "help":
            from .help_topics import HelpDialog
            HelpDialog(self).exec()
        elif key == "ready":
            self.accept()
            win.ready_check()
            return
        self.go(0)

    def done(self, r):  # noqa: D401 – uloží volbu „nezobrazovat“
        try:
            self.win.settings.setValue("pruvodce/skryt", self.cb_hide.isChecked())
        except AttributeError:
            pass
        super().done(r)
