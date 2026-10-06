"""Panel geodetických úloh (Qt). Výpočty samotné jsou v ``kontrola.geodezie.ulohy`` (sdílí je i webová verze)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QCompleter, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPlainTextEdit, QPushButton, QSplitter, QTextBrowser, QVBoxLayout,
                               QWidget)

from ..geodezie import ulohy as _U
from ..geodezie.ulohy import *  # noqa: F401,F403 – úlohy u_* a ULOHY pro zpětnou kompatibilitu
from ..geodezie.ulohy import ULOHY, ChybaVstupu, Pole, Vysledek, _f  # noqa: F401

globals().update({k: v for k, v in vars(_U).items() if k.startswith("_") and not k.startswith("__")})


class UlohyPanel(QWidget):
    pointsAdded = Signal(int)

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        sp = QSplitter()
        self.lst = QListWidget()
        for nazev, _p, _f, _fn in ULOHY:
            self.lst.addItem(nazev)
        self.lst.setMaximumWidth(260)
        self.lst.setObjectName("seznam_uloh")
        self.lst.setStyleSheet("QListWidget#seznam_uloh::item { padding: 7px 8px; }")
        levy = QWidget()
        levy.setMaximumWidth(260)
        ll = QVBoxLayout(levy)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)
        from PySide6.QtWidgets import QLineEdit
        self.hledat = QLineEdit()
        self.hledat.setPlaceholderText("Hledat úlohu (polygon, přesnost…)")
        self.hledat.setClearButtonEnabled(True)
        self.hledat.textChanged.connect(self.filtruj)
        ll.addWidget(self.hledat)
        ll.addWidget(self.lst, 1)
        sp.addWidget(levy)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.popis = QLabel()
        self.popis.setWordWrap(True)
        rl.addWidget(self.popis)
        self.formbox = QGroupBox("Zadání")
        self.form = QFormLayout(self.formbox)
        rl.addWidget(self.formbox)
        row = QHBoxLayout()
        self.b_calc = QPushButton("Vypočítat")
        self.b_calc.setProperty("primarni", True)
        self.b_calc.setShortcut("Ctrl+Return")
        self.b_add = QPushButton("Přidat do seznamu")
        self.b_add.setEnabled(False)
        self.b_copy = QPushButton("Kopírovat protokol")
        self.b_pdf = QPushButton("Protokol PDF…")
        self.b_pdf.setToolTip("Výpočetní protokol (tento výpočet, nebo všechny výpočty projektu) do PDF")
        for b in (self.b_calc, self.b_add, self.b_copy, self.b_pdf):
            row.addWidget(b)
        row.addStretch(1)
        rl.addLayout(row)
        self.chyba = QLabel()
        self.chyba.setWordWrap(True)
        rl.addWidget(self.chyba)
        self.vystup = QTextBrowser()
        self.vystup.setStyleSheet("font-family: Consolas, 'DejaVu Sans Mono', monospace;")
        rl.addWidget(self.vystup, 1)
        sp.addWidget(right)
        sp.setStretchFactor(1, 1)
        lay.addWidget(sp)
        self.inputs: dict[str, QWidget] = {}
        self.vysledek: Vysledek | None = None
        self._completer_model = QStringListModel(self)
        self.lst.currentRowChanged.connect(self._show)
        self.b_calc.clicked.connect(self.vypocitej)
        self.b_add.clicked.connect(self.pridej)
        self.b_copy.clicked.connect(self._copy)
        self.b_pdf.clicked.connect(lambda: self.protokol_pdf())
        self.lst.setCurrentRow(0)


    def filtruj(self, text: str):
        """Schová úlohy, které neodpovídají hledanému textu (bez ohledu na diakritiku, i v popisu)."""
        import unicodedata

        def bez(t: str) -> str:
            return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
        slova = bez(text).split()
        prvni = None
        for i, (nazev, popis, _pole, _fn) in enumerate(ULOHY):
            ok = all(w in bez(nazev + " " + popis) for w in slova)
            self.lst.item(i).setHidden(not ok)
            if ok and prvni is None:
                prvni = i
        cur = self.lst.currentItem()
        if prvni is not None and (cur is None or cur.isHidden()):
            self.lst.setCurrentRow(prvni)

    def _ze_souboru(self, pole: QPlainTextEdit):
        """Řádky (kontrolní body, délky, úhly…) z textového souboru, např. seznamu z kontrolního měření."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Řádky ze souboru", "",
                                              "Text (*.txt *.csv *.prn *.dat);;Vše (*)")
        if not path:
            return
        data = Path(path).read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1250", errors="replace")  # Groma, Kokeš
        pole.setPlainText(text.replace("\t", " "))

    def _show(self, i: int):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.inputs = {}
        nazev, popis, pole, _fn = ULOHY[i]
        self.popis.setText(f"<b style='font-size:12pt'>{escape(nazev)}</b><br>{escape(popis)}")
        self._completer_model.setStringList([b.cislo for b in self.page.seznam.body])
        for p in pole:
            if p.typ == "volba":
                w = QComboBox()
                w.addItems(list(p.volby))
                w.setCurrentText(p.vychozi)
            elif p.typ == "radky":
                w = QPlainTextEdit()
                w.setFixedHeight(90)
                w.setPlaceholderText(p.label)
                obal = QWidget()
                ol = QHBoxLayout(obal)
                ol.setContentsMargins(0, 0, 0, 0)
                ol.addWidget(w, 1)
                b = QPushButton("Ze souboru…")
                b.setToolTip("Načíst řádky z textového souboru (mezery i tabulátory, i seznam souřadnic)")
                b.clicked.connect(lambda _c=False, pole=w: self._ze_souboru(pole))
                ol.addWidget(b, 0, Qt.AlignTop)
            else:
                w = QLineEdit(p.vychozi)
                if p.typ == "bod":
                    c = QCompleter(self._completer_model, w)
                    c.setCaseSensitivity(Qt.CaseInsensitive)
                    c.setFilterMode(Qt.MatchStartsWith)
                    w.setCompleter(c)
                    w.setPlaceholderText("číslo bodu ze seznamu")
            if p.napoveda:
                w.setToolTip(p.napoveda)
            self.form.addRow(p.label + ":", obal if p.typ == "radky" else w)
            self.inputs[p.key] = w
        self.vysledek = None
        self.b_add.setEnabled(False)
        self.chyba.clear()

    def hodnoty(self) -> dict:
        out = {}
        for k, w in self.inputs.items():
            if isinstance(w, QComboBox):
                out[k] = w.currentText()
            elif isinstance(w, QPlainTextEdit):
                out[k] = w.toPlainText()
            else:
                out[k] = w.text()
        return out

    def nastav(self, **hodnoty):
        for k, v in hodnoty.items():
            w = self.inputs[k]
            if isinstance(w, QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(str(v))
            else:
                w.setText(str(v))

    def vypocitej(self) -> Vysledek | None:
        i = self.lst.currentRow()
        nazev, _p, _pole, fn = ULOHY[i]
        try:
            self.vysledek = fn(self.page.seznam, self.hodnoty())
        except ChybaVstupu as e:
            self.chyba.setText(f"<span style='color:#DC2626'>⚠ {escape(str(e))}</span>")
            self.vysledek = None
            self.b_add.setEnabled(False)
            return None
        except Exception as e:  # noqa: BLE001 – výpočet nesmí shodit aplikaci
            self.chyba.setText(f"<span style='color:#DC2626'>⚠ Výpočet se nepovedl: {escape(str(e))}</span>")
            self.vysledek = None
            return None
        self.chyba.clear()
        self.vystup.setPlainText("\n".join(self.vysledek.protokol))
        self.b_add.setEnabled(bool(self.vysledek.nove))
        self.page.protokol_append(self.vysledek.protokol)
        return self.vysledek

    def pridej(self) -> int:
        if not self.vysledek or not self.vysledek.nove:
            return 0
        n, konf = self.page.seznam.pridej(self.vysledek.nove, f"{ULOHY[self.lst.currentRow()][0]}: nové body")
        self.page.model.refresh()
        self.page._after_change()
        if konf:
            self.chyba.setText("<span style='color:#B45309'>Body " + ", ".join(konf) + " už v seznamu jsou – "
                               "nepřepsaly se (zvolte jiné číslo nebo bod v seznamu nejdřív smažte).</span>")
        else:
            self.chyba.setText(f"<span style='color:#16A34A'>✓ Přidáno do seznamu: {n} bodů.</span>")
        self.pointsAdded.emit(n)
        return n

    def protokol_pdf(self, cesta: str | None = None, vse: bool | None = None):
        """Uloží protokol do PDF: buď poslední výpočet, nebo celý protokol projektu (všechny výpočty)."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from ..geodezie.protokol import protokol_pdf
        celek = None
        p = getattr(self.page, "_path", None)
        if p is not None and p.with_name("protokol.txt").exists():
            celek = p.with_name("protokol.txt").read_text(encoding="utf-8")
        if vse is None:
            if celek and self.vystup.toPlainText().strip():
                r = QMessageBox.question(self, "Protokol PDF", "Uložit protokol všech výpočtů projektu?\n\n"
                                         "Ano = všechny výpočty, Ne = jen poslední výpočet.",
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                if r == QMessageBox.Cancel:
                    return None
                vse = r == QMessageBox.Yes
            else:
                vse = bool(celek) and not self.vystup.toPlainText().strip()
        text = celek if vse else self.vystup.toPlainText()
        if not (text or "").strip():
            self.chyba.setText("<span style='color:#B45309'>Zatím není co uložit – nejdřív něco vypočítejte.</span>")
            return None
        if cesta is None:
            cesta, _ = QFileDialog.getSaveFileName(self, "Protokol do PDF", "protokol_vypoctu.pdf", "PDF (*.pdf)")
            if not cesta:
                return None
        win = getattr(self.page, "win", None)
        pr = getattr(win, "project", None) if win is not None else None
        nazev = getattr(pr, "name", "") if pr is not None else ""
        out = protokol_pdf(text, cesta, nazev=f"Výpočetní protokol {nazev}".strip())
        self.chyba.setText(f"<span style='color:#16A34A'>✓ Protokol uložen: {out}</span>")
        return out

    def _copy(self):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.vystup.toPlainText())


def protokol_path(root: Path) -> Path:
    return Path(root) / "vypocty" / "protokol.txt"
