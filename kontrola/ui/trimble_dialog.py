"""Okno „Trimble – export podle šablony“ (jako Trimble File and Report): JobXML + šablona .xsl → protokol,
seznam bodů, zápisník… Výsledek jde uložit nebo rovnou načíst do seznamu souřadnic."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from ..io.trimble import TrimbleError, exportuj

KLIC = "vypocty/trimble_sablony"


def pripona(text: str) -> str:
    t = text.lstrip()[:400].lower()
    if "w:worddocument" in t or "mso-application" in t:
        return ".doc"
    if t.startswith("<html") or "<!doctype html" in t:
        return ".html"
    if t.startswith("<?xml"):
        return ".xml"
    return ".txt"


class TrimbleDialog(QDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(parent)
        self.page = page
        self.setWindowTitle("Trimble – export podle šablony (File and Report)")
        self.resize(900, 620)
        lay = QVBoxLayout(self)
        info = QLabel("Vyberte zakázku JobXML (.jxl) a šablonu (.xsl). Soubory .xdt, které šablona vkládá "
                      "(např. Protokol-Head.xdt s hlavičkou firmy), musí být ve stejné složce jako šablona. "
                      "Zakázku .job nejdřív exportujte v kontroléru jako JobXML.")
        info.setWordWrap(True)
        info.setObjectName("stranka_info")
        lay.addWidget(info)
        g = QGridLayout()
        self.zdroj = QLineEdit()
        self.sablona = QComboBox()
        self.sablona.setEditable(True)
        for c in self._sablony():
            self.sablona.addItem(Path(c).stem, c)
        b1, b2 = QPushButton("Procházet…"), QPushButton("Procházet…")
        g.addWidget(QLabel("Zdrojový soubor:"), 0, 0)
        g.addWidget(self.zdroj, 0, 1)
        g.addWidget(b1, 0, 2)
        g.addWidget(QLabel("Šablona:"), 1, 0)
        g.addWidget(self.sablona, 1, 1)
        g.addWidget(b2, 1, 2)
        lay.addLayout(g)
        row = QHBoxLayout()
        self.b_export = QPushButton("Exportovat")
        self.b_export.setProperty("primarni", True)
        self.b_ulozit = QPushButton("Uložit…")
        self.b_seznam = QPushButton("Do seznamu souřadnic…")
        self.b_seznam.setToolTip("Výstup šablony se seznamem bodů (číslo Y X Z) načíst do Výpočtů")
        for b in (self.b_export, self.b_ulozit, self.b_seznam):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.zprava = QLabel()
        self.zprava.setWordWrap(True)
        lay.addWidget(self.zprava)
        self.nahled = QPlainTextEdit()
        self.nahled.setReadOnly(True)
        self.nahled.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.nahled.setObjectName("vypis")
        lay.addWidget(self.nahled, 1)
        self.vystup = ""
        b1.clicked.connect(self._vyber_zdroj)
        b2.clicked.connect(self._vyber_sablonu)
        self.b_export.clicked.connect(lambda: self.exportovat())
        self.b_ulozit.clicked.connect(lambda: self.ulozit())
        self.b_seznam.clicked.connect(lambda: self.do_seznamu())
        self._tlacitka()

    # ------------------------------------------------------------ šablony (naposledy použité)
    @staticmethod
    def _sablony() -> list[str]:
        v = QSettings().value(KLIC, []) or []
        v = [v] if isinstance(v, str) else list(v)
        return [c for c in v if Path(c).is_file()]

    def nastav_sablonu(self, cesta: str) -> None:
        sab = [c for c in self._sablony() if c != cesta]
        QSettings().setValue(KLIC, ([cesta] + sab)[:15])
        i = self.sablona.findData(cesta)
        if i < 0:
            self.sablona.insertItem(0, Path(cesta).stem, cesta)
            i = 0
        self.sablona.setCurrentIndex(i)

    def _vyber_zdroj(self):
        c, _ = QFileDialog.getOpenFileName(self, "Zakázka Trimble", "", "JobXML (*.jxl *.xml);;Zakázka (*.job)")
        if c:
            self.zdroj.setText(c)

    def _vyber_sablonu(self):
        c, _ = QFileDialog.getOpenFileName(self, "Šablona exportu", "", "Šablona (*.xsl *.XSL)")
        if c:
            self.nastav_sablonu(c)

    def _tlacitka(self):
        self.b_ulozit.setEnabled(bool(self.vystup))
        self.b_seznam.setEnabled(bool(self.vystup) and pripona(self.vystup) == ".txt" and self.page is not None)

    # ------------------------------------------------------------ export
    def exportovat(self) -> str:
        sab = self.sablona.currentData() or self.sablona.currentText()
        if not self.zdroj.text() or not sab:
            self.zprava.setText("Vyberte zdrojový soubor i šablonu.")
            return ""
        try:
            self.vystup = exportuj(self.zdroj.text(), sab)
        except (TrimbleError, OSError) as e:
            self.vystup = ""
            self.zprava.setText(f"<span style='color:#B45309'>⚠ {e}</span>")
        else:
            self.nastav_sablonu(str(sab))
            p = pripona(self.vystup)
            self.zprava.setText(f"✓ Hotovo – {len(self.vystup.splitlines())} řádků"
                                + (" (dokument pro Word – uložte ho a otevřete ve Wordu)" if p == ".doc" else ""))
        self.nahled.setPlainText(self.vystup[:200_000])
        self._tlacitka()
        return self.vystup

    def ulozit(self, cesta: str | None = None) -> Path | None:
        if not self.vystup:
            return None
        if cesta is None:
            navrh = Path(self.zdroj.text()).with_suffix(pripona(self.vystup))
            cesta, _ = QFileDialog.getSaveFileName(self, "Uložit výstup", str(navrh))
            if not cesta:
                return None
        p = Path(cesta)
        # textové výstupy jako ve File and Report (Windows-1250), znaky mimo něj se nahradí
        if pripona(self.vystup) == ".txt":
            p.write_bytes(self.vystup.replace("\r\n", "\n").replace("\n", "\r\n").encode("cp1250", "replace"))
        else:
            p.write_text(self.vystup, encoding="utf-8")
        self.zprava.setText(f"✓ Uloženo: {p}")
        return p

    def do_seznamu(self):
        if not self.vystup or self.page is None:
            return None
        import tempfile
        p = Path(tempfile.mkdtemp()) / (Path(self.zdroj.text()).stem + "_body.txt")
        p.write_text(self.vystup, encoding="utf-8")
        return self.page.import_dialog(str(p))
