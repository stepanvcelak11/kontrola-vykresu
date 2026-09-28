"""Okno „Kontrola výpočtu souřadnic“: zápisník + dané body → výpočet → porovnání se seznamem studenta."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from ..checks.seznam import read_point_list
from ..vypocet import compare, compute, read_zap, text_report
from .theme import fit_headers


class VypocetDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Kontrola výpočtu souřadnic (zápisník z totální stanice)")
        self.resize(1000, 720)
        self.report = ""
        lay = QVBoxLayout(self)
        intro = QLabel("Program sám spočítá souřadnice podrobných bodů ze zápisníku (polární metoda stejně jako "
                       "Groma: dvě polohy dalekohledu, vodorovná délka × měřítkový koeficient, orientační posun "
                       "vážený délkami, výšky od nivelačního bodu) a porovná je s vaším seznamem souřadnic.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        meta = project.meta.setdefault("vypocet", {}) if project else {}
        self.zap = self._file_row(form, "Zápisník (.zap):", meta.get("zapisnik", ""),
                                  "Zápisník (*.zap *.txt);;Vše (*)")
        self.dane = self._file_row(form, "Dané body (Y X Z):", meta.get("dane", ""),
                                   "Seznam (*.txt *.crd *.csv);;Vše (*)", multi=True,
                                   tip="Stanoviska (např. gnss_husovice.txt) a orientační / nivelační body "
                                       "z ČÚZK. Více souborů oddělte středníkem.")
        default_seznam = meta.get("seznam", "")
        if not default_seznam and project is not None:
            s = project.attachments("seznamy")
            default_seznam = str(s[0].path) if s else ""
        self.seznam = self._file_row(form, "Váš seznam souřadnic:", default_seznam,
                                     "Seznam (*.txt *.crd *.csv);;Vše (*)")
        krow = QHBoxLayout()
        self.k_auto = QCheckBox("spočítat (Křovák + nadmořská výška)")
        self.k_auto.setChecked(meta.get("koeficient") in (None, ""))
        self.k = QDoubleSpinBox()
        self.k.setDecimals(10)
        self.k.setRange(0.99, 1.01)
        self.k.setSingleStep(0.000001)
        self.k.setValue(float(meta.get("koeficient") or 0.9999))
        self.k.setEnabled(not self.k_auto.isChecked())
        self.k_auto.toggled.connect(lambda on: self.k.setEnabled(not on))
        krow.addWidget(self.k_auto)
        krow.addWidget(self.k)
        krow.addWidget(QLabel("(nebo opište z protokolu Gromy – „Měřítkový koeficient“)"))
        krow.addStretch(1)
        form.addRow("Měřítkový koeficient:", krow)
        trow = QHBoxLayout()
        self.tol_xy = QDoubleSpinBox()
        self.tol_xy.setDecimals(3)
        self.tol_xy.setRange(0.001, 1.0)
        self.tol_xy.setValue(float(meta.get("tol_xy", 0.01)))
        self.tol_xy.setSuffix(" m")
        self.tol_z = QDoubleSpinBox()
        self.tol_z.setDecimals(3)
        self.tol_z.setRange(0.001, 1.0)
        self.tol_z.setValue(float(meta.get("tol_z", 0.01)))
        self.tol_z.setSuffix(" m")
        trow.addWidget(QLabel("poloha"))
        trow.addWidget(self.tol_xy)
        trow.addWidget(QLabel("výška"))
        trow.addWidget(self.tol_z)
        trow.addStretch(1)
        form.addRow("Povolený rozdíl:", trow)
        lay.addLayout(form)

        brow = QHBoxLayout()
        self.b_run = QPushButton("Spočítat a porovnat")
        self.b_run.setProperty("primarni", True)
        self.b_run.setDefault(True)
        self.b_run.clicked.connect(self.run)
        self.b_save = QPushButton("Uložit protokol…")
        self.b_save.clicked.connect(self.save_report)
        self.b_save.setEnabled(False)
        self.b_coords = QPushButton("Uložit vypočtené souřadnice…")
        self.b_coords.clicked.connect(self.save_coords)
        self.b_coords.setEnabled(False)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        for b in (self.b_run, self.b_save, self.b_coords):
            brow.addWidget(b)
        brow.addWidget(self.summary, 1)
        lay.addLayout(brow)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Bod", "Stanovisko", "dY [m]", "dX [m]", "dZ [m]", "Výsledek",
                                              "Vypočteno Y X Z"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        for c, w in enumerate((150, 110, 80, 80, 80, 220)):
            self.table.setColumnWidth(c, w)
        fit_headers(self.table)
        lay.addWidget(self.table, 3)
        self.log = QTextBrowser()
        self.log.setMaximumHeight(150)
        lay.addWidget(self.log, 1)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.accept)
        crow = QHBoxLayout()
        crow.addStretch(1)
        crow.addWidget(close)
        lay.addLayout(crow)
        self.result = None

    def _file_row(self, form, label, value, filt, multi=False, tip=""):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        ed = QLineEdit(value)
        if tip:
            ed.setToolTip(tip)
        b = QPushButton("Vybrat…")
        b.setAutoDefault(False)

        def pick():
            if multi:
                fs, _ = QFileDialog.getOpenFileNames(self, label, "", filt)
                if fs:
                    ed.setText("; ".join(fs))
            else:
                f, _ = QFileDialog.getOpenFileName(self, label, "", filt)
                if f:
                    ed.setText(f)
        b.clicked.connect(pick)
        h.addWidget(ed, 1)
        h.addWidget(b)
        form.addRow(label, w)
        return ed

    def run(self):
        zap = self.zap.text().strip()
        dane = [s.strip() for s in self.dane.text().split(";") if s.strip()]
        seznam = self.seznam.text().strip()
        missing = [n for n, v in (("zápisník", zap), ("dané body", dane), ("váš seznam", seznam)) if not v]
        if missing:
            QMessageBox.information(self, "Kontrola výpočtu", "Vyberte: " + ", ".join(missing) + ".")
            return
        try:
            stations = read_zap(zap)
            known = [p for f in dane for p in read_point_list(f)]
            student = read_point_list(seznam)
        except OSError as exc:
            QMessageBox.warning(self, "Kontrola výpočtu", f"Soubor nelze načíst: {exc}")
            return
        if not stations:
            QMessageBox.warning(self, "Kontrola výpočtu", "V zápisníku nejsou žádná stanoviska "
                                "(očekává se formát Gromy: „1 <stanovisko> <výška přístroje> *“).")
            return
        k = None if self.k_auto.isChecked() else self.k.value()
        res = compute(stations, known, k)
        bad, rows = compare(res, student, self.tol_xy.value(), self.tol_z.value(), known=known)
        self.result = res
        self.report = text_report(res, rows, bad)
        if self.project is not None:
            self.project.meta["vypocet"] = {"zapisnik": zap, "dane": "; ".join(dane), "seznam": seznam,
                                            "koeficient": k, "tol_xy": self.tol_xy.value(),
                                            "tol_z": self.tol_z.value()}
            self.project.save()
        self._fill(rows)
        self.log.setPlainText("\n".join(res.zpravy))
        n = sum(1 for r in rows if r.vypocet is not None and r.student is not None)
        if not res.body:
            self.summary.setText("<span style='color:#B91C1C'><b>Nic se nespočítalo</b> – viz zprávy dole.</span>")
        elif bad:
            self.summary.setText(f"<span style='color:#B91C1C'><b>{len(bad)} rozdílů</b></span> z {n} porovnaných "
                                 "bodů. Zkontrolujte výpočet v Gromě (dané body, výšky, koeficient).")
        else:
            self.summary.setText(f"<span style='color:#15803D'><b>✓ Výpočet souhlasí</b></span> – {n} bodů, "
                                 "všechny rozdíly v povolené toleranci.")
        self.b_save.setEnabled(True)
        self.b_coords.setEnabled(bool(res.body))

    def _fill(self, rows):
        self.table.setRowCount(0)
        def num(b):
            import re as _re
            d = _re.sub(r"\D", "", b)
            return (0, int(d[-6:])) if d else (1, 0)
        rows = sorted(rows, key=lambda r: (r.poznamka == "v pořádku", num(r.bod), r.bod))
        f = lambda v: "–" if v is None else f"{v:+.3f}"  # noqa: E731
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            calc = ""
            if r.vypocet is not None:
                z = "" if r.vypocet.z is None else f" {r.vypocet.z:.3f}"
                calc = f"{r.vypocet.y:.3f} {r.vypocet.x:.3f}{z}"
            vals = [r.bod, r.stanovisko, f(r.dy), f(r.dx), f(r.dz), r.poznamka, calc]
            ok = r.poznamka == "v pořádku"
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (2, 3, 4):
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if not ok:
                    it.setForeground(QBrush(QColor(185, 28, 28)))
                    if c == 5:
                        f_ = it.font()
                        f_.setBold(True)
                        it.setFont(f_)
                self.table.setItem(i, c, it)

    def save_report(self):
        p, _ = QFileDialog.getSaveFileName(self, "Uložit protokol", "kontrola_vypoctu.txt", "Text (*.txt)")
        if p:
            Path(p).write_text(self.report, encoding="utf-8-sig")

    def save_coords(self):
        if self.result is None:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Uložit vypočtené souřadnice", "vypoctene_body.txt", "Text (*.txt)")
        if not p:
            return
        lines = [f"{b.bod:<18}{b.y:>13.3f}{b.x:>14.3f}{'' if b.z is None else f'{b.z:>10.3f}'}"
                 for b in self.result.body if not b.kontrolni]
        Path(p).write_text("\n".join(lines) + "\n", encoding="utf-8")
