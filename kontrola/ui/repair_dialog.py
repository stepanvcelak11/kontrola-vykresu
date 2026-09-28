"""Dialog automatické opravy výkresu (výsledek se uloží do nového DXF)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout)

from ..repair import RepairOptions


class RepairDialog(QDialog):
    def __init__(self, source: str, tolerance: float, has_rules: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Automatická oprava výkresu")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        info = QLabel(f"Opraví jednoznačné chyby do tolerance {tolerance:g} m (jako režim „oprava“ "
                      "v MGEO). Původní výkres zůstane beze změny – opravený se uloží do nového DXF, "
                      "který se pak otevře a znovu zkontroluje. Upravují se entity LINE a LWPOLYLINE.")
        info.setWordWrap(True)
        lay.addWidget(info)
        box = QGroupBox("Co opravit")
        bl = QVBoxLayout(box)
        defaults = RepairOptions()
        self.boxes: dict[str, QCheckBox] = {}
        for key, label in RepairOptions.LABELS.items():
            cb = QCheckBox(label)
            cb.setChecked(getattr(defaults, key))
            if key == "symbologie":
                cb.setEnabled(has_rules)
                if not has_rules:
                    cb.setToolTip("Nejsou načtena pravidla.")
            self.boxes[key] = cb
            bl.addWidget(cb)
        lay.addWidget(box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Uložit do:"))
        src = Path(source)
        self.out = QLineEdit(str(src.with_name(src.stem + "_opraveno.dxf")))
        row.addWidget(self.out, 1)
        b = QPushButton("…")
        b.clicked.connect(self._pick)
        row.addWidget(b)
        lay.addLayout(row)
        lay.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Opravit")
        bb.button(QDialogButtonBox.Cancel).setText("Zrušit")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick(self):
        p, _ = QFileDialog.getSaveFileName(self, "Uložit opravený výkres", self.out.text(), "DXF (*.dxf)")
        if p:
            self.out.setText(p)

    def options(self) -> RepairOptions:
        return RepairOptions(**{k: cb.isChecked() for k, cb in self.boxes.items()})

    def out_path(self) -> str:
        p = self.out.text().strip()
        return p if p.lower().endswith(".dxf") else p + ".dxf"
