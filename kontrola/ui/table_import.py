"""Průvodce importem tabulky atributů: náhled, přiřazení sloupců, souhrn."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..importer.table import (FIELDS, ImportResult, TableData, detect_header_row, generate_rules,
                              guess_mapping, read_table)


def col_name(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class TableImportWizard(QDialog):
    """Náhled tabulky a přiřazení sloupců k polím pravidel."""

    def __init__(self, path: str, parent=None, mapping: dict | None = None, header_row: int | None = None,
                 sheet: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Import tabulky atributů")
        self.resize(1150, 720)
        self.path = path
        self.data: TableData = read_table(path, sheet)
        self.result: ImportResult | None = None
        self._combos: dict[str, QComboBox] = {}

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(f"<b>{self.data.path.split('/')[-1].split(chr(92))[-1]}</b>"))
        self.sheet = QComboBox()
        if self.data.sheets:
            top.addWidget(QLabel("List:"))
            self.sheet.addItems(self.data.sheets)
            self.sheet.setCurrentText(self.data.sheet or "")
            self.sheet.currentTextChanged.connect(self._sheet_changed)
            top.addWidget(self.sheet)
        top.addWidget(QLabel("Řádek s hlavičkou:"))
        self.header = QSpinBox()
        self.header.setRange(0, max(1, len(self.data.rows)))
        self.header.setSpecialValueText("bez hlavičky")
        self.header.valueChanged.connect(self._header_changed)
        top.addWidget(self.header)
        b_guess = QPushButton("Odhadnout sloupce znovu")
        b_guess.clicked.connect(self._guess)
        top.addWidget(b_guess)
        top.addStretch(1)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.preview = QTableWidget()
        self.preview.setEditTriggers(QTableWidget.NoEditTriggers)
        split.addWidget(self.preview)

        right = QWidget()
        rl = QVBoxLayout(right)
        box = QGroupBox("Přiřazení sloupců")
        fl = QFormLayout(box)
        for key, label in FIELDS:
            cb = QComboBox()
            cb.currentIndexChanged.connect(self._update_summary)
            self._combos[key] = cb
            fl.addRow(label + ":", cb)
        rl.addWidget(box)
        hint = QLabel("Povolené hodnoty lze zapsat jako „lípa, dub“ (platí pro první povinný atribut) "
                      "nebo „DRUH=lípa,dub; MATERIAL=zděná“. Typ geometrie: bod / linie / plocha "
                      "(polygon) / text. Barva: číslo nebo název (červená…).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        rl.addWidget(hint)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        rl.addWidget(self.summary)
        rl.addStretch(1)
        split.addWidget(right)
        split.setSizes([760, 380])
        lay.addWidget(split, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Vytvořit pravidla")
        bb.button(QDialogButtonBox.Cancel).setText("Zrušit")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._fill_preview()
        if header_row is not None or mapping:
            self._apply(header_row, mapping or {})
        else:
            self._guess()

    # ------------------------------------------------------------
    def _sheet_changed(self, name: str):
        self.data = read_table(self.path, name)
        self._fill_preview()
        self._guess()

    def _fill_preview(self):
        rows = self.data.rows[:300]
        n = self.data.ncols
        self.preview.clear()
        self.preview.setRowCount(len(rows))
        self.preview.setColumnCount(n)
        self.preview.setHorizontalHeaderLabels([col_name(i) for i in range(n)])
        for r, row in enumerate(rows):
            for c in range(n):
                self.preview.setItem(r, c, QTableWidgetItem(row[c] if c < len(row) else ""))
        self.preview.resizeColumnsToContents()
        for c in range(n):
            self.preview.setColumnWidth(c, min(self.preview.columnWidth(c), 220))
        self._fill_combos()

    def _fill_combos(self):
        hi = self.header.value() - 1
        header = self.data.rows[hi] if 0 <= hi < len(self.data.rows) else []
        for cb in self._combos.values():
            cur = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("(nepoužít)", None)
            for c in range(self.data.ncols):
                h = header[c] if c < len(header) else ""
                cb.addItem(f"{col_name(c)}: {h}" if h else col_name(c), c)
            idx = cb.findData(cur)
            cb.setCurrentIndex(max(0, idx))
            cb.blockSignals(False)

    def _header_changed(self):
        self._fill_combos()
        self._highlight_header()
        self._update_summary()

    def _highlight_header(self):
        hi = self.header.value() - 1
        for r in range(self.preview.rowCount()):
            for c in range(self.preview.columnCount()):
                it = self.preview.item(r, c)
                if it is None:
                    continue
                if r == hi:
                    it.setBackground(QBrush(QColor(255, 235, 150)))
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                elif r < hi:
                    it.setForeground(QBrush(QColor(160, 160, 160)))
                    it.setBackground(QBrush())
                else:
                    it.setForeground(QBrush())
                    it.setBackground(QBrush())

    def _guess(self):
        hi = detect_header_row(self.data.rows)
        mapping = guess_mapping(self.data.rows[hi]) if hi is not None else {}
        self._apply(hi, mapping)

    def _apply(self, header_row: int | None, mapping: dict):
        self.header.blockSignals(True)
        self.header.setValue((header_row + 1) if header_row is not None else 0)
        self.header.blockSignals(False)
        self._fill_combos()
        for key, cb in self._combos.items():
            cb.blockSignals(True)
            cb.setCurrentIndex(max(0, cb.findData(mapping.get(key))))
            cb.blockSignals(False)
        self._highlight_header()
        self._update_summary()

    def mapping(self) -> dict[str, int]:
        return {k: cb.currentData() for k, cb in self._combos.items() if cb.currentData() is not None}

    def header_row(self) -> int | None:
        v = self.header.value()
        return v - 1 if v > 0 else None

    def _update_summary(self, *_):
        res = generate_rules(self.data.rows, self.header_row(), self.mapping(), self.path)
        s = f"<b>Náhled:</b> {res.summary()}"
        if res.errors:
            s += "<br><span style='color:#c00'>" + "<br>".join(res.errors[:6]) + (
                "<br>…" if len(res.errors) > 6 else "") + "</span>"
        self.summary.setText(s)

    def _accept(self):
        self.result = generate_rules(self.data.rows, self.header_row(), self.mapping(), self.path)
        if not self.result.rules.pravidla:
            QMessageBox.warning(self, "Import tabulky", "Nevzniklo žádné pravidlo. Zkontrolujte řádek "
                                                        "s hlavičkou a přiřazení sloupců.\n\n"
                                + "\n".join(self.result.errors[:10]))
            return
        self.accept()


class ImportSummaryDialog(QDialog):
    def __init__(self, result: ImportResult, added: int, replaced: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Souhrn importu")
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        lab = QLabel(f"<h3>{result.summary()}</h3>Do projektu přidáno {added} nových pravidel, "
                     f"{replaced} existujících pravidel se stejným kódem bylo nahrazeno.<br>"
                     "Pravidla si můžete prohlédnout a upravit na záložce <b>Pravidla</b>.")
        lab.setWordWrap(True)
        lay.addWidget(lab)
        if result.errors:
            lay.addWidget(QLabel("<b>Řádky, které se nepodařilo zpracovat:</b>"))
            lw = QListWidget()
            lw.addItems(result.errors)
            lay.addWidget(lw, 1)
        if result.warnings:
            lay.addWidget(QLabel("<b>Zpracováno s upozorněním:</b>"))
            lw2 = QListWidget()
            lw2.addItems(result.warnings)
            lay.addWidget(lw2, 1)
        if not result.errors and not result.warnings:
            lay.addWidget(QLabel("Všechny řádky byly zpracovány bez problémů."))
            lay.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
