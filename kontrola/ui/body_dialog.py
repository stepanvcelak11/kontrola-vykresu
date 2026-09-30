"""Okno „Body do výkresu (DXF)“: seznam souřadnic → DXF se značkami, čísly a výškami podle Směrnice."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout)

from ..checks.seznam import read_point_list
from ..export.body_dxf import Moznosti, export_points_dxf, guess_rules


class BodyDialog(QDialog):
    def __init__(self, win, path: str = "", points=None):
        super().__init__(win)
        self.win = win
        self.points = points  # body přímo z výpočtu (Groma v aplikaci)
        self.setWindowTitle("Body do výkresu (DXF)")
        self.resize(640, 420)
        rs = win.project.rules
        lay = QVBoxLayout(self)
        intro = QLabel("Z bodů vytvoří DXF se <b>značkou bodu</b>, <b>číslem</b> a <b>výškou</b> na vrstvách, s barvou, "
                       "tloušťkou a písmem podle pravidel (Směrnice + Word se zadáním) – místo ručního importu "
                       "z Gromy. Popisy jsou rozmístěné jako v Gromě: číslo vpravo nahoře, výška vpravo dole.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        row = QHBoxLayout()
        self.path = QLineEdit(path)
        self.path.setPlaceholderText("Seznam souřadnic (číslo Y X Z)")
        b = QPushButton("Vybrat…")
        b.clicked.connect(self._pick)
        row.addWidget(self.path, 1)
        row.addWidget(b)
        if points is not None:
            self.path.setText(f"{len(points)} bodů z výpočtu ze zápisníku")
            self.path.setEnabled(False)
            b.setEnabled(False)
        form.addRow("Body:", row)
        guess = guess_rules(rs)
        self.combos = {}
        for key, label in (("bod", "Značka bodu:"), ("cislo", "Číslo bodu:"), ("vyska", "Výška bodu:")):
            cb = QComboBox()
            cb.addItem("(nevkládat)", None)
            for i, r in enumerate(rs.pravidla):
                cb.addItem(f"{r.nazev or r.kod} – vrstva {r.hladina}", i)
            if guess.get(key) is not None:
                cb.setCurrentIndex(rs.pravidla.index(guess[key]) + 1)
            self.combos[key] = cb
            form.addRow(label, cb)
        self.short = QCheckBox("Číslo bodu zkráceně (1000130001 → 1)")
        self.short.setChecked(True)
        form.addRow("", self.short)
        self.dec = QSpinBox()
        self.dec.setRange(0, 3)
        self.dec.setValue(2)
        form.addRow("Desetinná místa výšky:", self.dec)
        lay.addLayout(form)
        if not rs.pravidla:
            warn = QLabel("<span style='color:#B45309'>V projektu nejsou pravidla – nahrajte nejdřív Směrnici "
                          "(Zadání), jinak nebude jasné, na jaké vrstvy body patří.</span>")
            warn.setWordWrap(True)
            lay.addWidget(warn)
        how = QLabel("V MicroStationu: DXF otevřete, nebo ho připojte jako referenci (Soubor → Reference) a prvky "
                     "zkopírujte do svého výkresu. Pak zkontrolujte: <b>Ověřit seznam souřadnic</b>.")
        how.setWordWrap(True)
        how.setObjectName("karta_popis")
        lay.addWidget(how)
        lay.addStretch(1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        ok = QPushButton("Vytvořit DXF…")
        ok.setProperty("primarni", True)
        ok.setDefault(True)
        ok.clicked.connect(self.create)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.reject)
        brow.addWidget(ok)
        brow.addWidget(close)
        lay.addLayout(brow)

    def _pick(self):
        f, _ = QFileDialog.getOpenFileName(self, "Seznam souřadnic", "", "Seznam (*.txt *.csv *.xyz);;Vše (*)")
        if f:
            self.path.setText(f)

    def create(self):
        rs = self.win.project.rules
        if self.points is not None:
            pts = self.points
        else:
            try:
                pts = read_point_list(self.path.text().strip())
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Body do DXF", f"Seznam nelze načíst: {exc}")
                return
        if not pts:
            QMessageBox.warning(self, "Body do DXF", "Nejsou žádné body.")
            return
        rules = {k: (rs.pravidla[cb.currentData()] if cb.currentData() is not None else None)
                 for k, cb in self.combos.items()}
        if not any(rules.values()):
            QMessageBox.information(self, "Body do DXF", "Vyberte aspoň jedno pravidlo (značku, číslo nebo výšku).")
            return
        default = Path(self.path.text()).with_name(Path(self.path.text()).stem + "_body.dxf") \
            if self.points is None else Path.home() / "body_z_vypoctu.dxf"
        out, _ = QFileDialog.getSaveFileName(self, "Uložit DXF s body", str(default), "DXF (*.dxf)")
        if not out:
            return
        existing = list(self.win.drawing.layers) if getattr(self.win, "drawing", None) is not None else []
        info = export_points_dxf(pts, rs, out, rules, Moznosti(self.short.isChecked(), True, self.dec.value()),
                                 existing)
        self.result_path = out
        QMessageBox.information(self, "Body do DXF",
                                f"Uloženo: {out}\n\nZnaček bodů: {info['bodu']}, čísel: {info['cisel']}, výšek: "
                                f"{info['vysek']}\nVrstvy: " + ", ".join(info["vrstvy"]))
        self.accept()
