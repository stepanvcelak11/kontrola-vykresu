"""Dialog nastavení kontrol: tolerance, zapnutí/vypnutí, závažnost a parametry."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from ..checks.base import REGISTRY, Severity
from ..config import Config
from ..rules import RuleSet, load_ms_color_table


def _dspin(value: float, decimals=4, maximum=1e9, minimum=0.0, step=0.01) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setDecimals(decimals)
    w.setRange(minimum, maximum)
    w.setSingleStep(step)
    w.setValue(float(value))
    return w


def _lab(text: str) -> QLabel:
    """Popisky polí stejně široké ve všech skupinách – pole jsou pod sebou zarovnaná."""
    lab = QLabel(text)
    lab.setMinimumWidth(300)
    lab.setWordWrap(True)
    return lab


class SettingsDialog(QDialog):
    def __init__(self, config: Config, rules: RuleSet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nastavení kontrol")
        self.resize(760, 720)
        self.config = copy.deepcopy(config)
        self.rules = rules
        self._editors: dict[str, dict] = {}

        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # --- obecné
        gen = QWidget()
        fl = QFormLayout(gen)
        self.tol = _dspin(self.config.tolerance, 4, 100)
        self.tol.setSuffix(" m")
        self.tol.setToolTip("Do této vzdálenosti se hledají chybějící napojení, body blízko sebe a mezery.")
        self.prec = _dspin(self.config.presnost, 6, 1, step=0.0001)
        self.prec.setSuffix(" m")
        self.prec.setToolTip("Body bližší než tato hodnota se považují za totožné (přesné napojení).")
        self.radius = _dspin(self.config.okruh_textu, 2, 1000, step=0.5)
        self.radius.setSuffix(" m")
        self.max_issues = QSpinBox()
        self.max_issues.setRange(10, 1_000_000)
        self.max_issues.setValue(self.config.max_chyb_na_kontrolu)
        self.ignored = QLineEdit(", ".join(self.config.ignorovane_hladiny))
        self.oda = QLineEdit(self.config.oda_cesta)
        b_oda = QPushButton("Vybrat…")
        b_oda.clicked.connect(self._pick_oda)
        row = QHBoxLayout()
        row.addWidget(self.oda, 1)
        row.addWidget(b_oda)
        fl.addRow("Tolerance:", self.tol)
        fl.addRow("Přesnost (totožnost bodů):", self.prec)
        fl.addRow("Okruh hledání textu k prvku:", self.radius)
        fl.addRow("Max. počet chyb jedné kontroly:", self.max_issues)
        fl.addRow("Ignorované vrstvy:", self.ignored)
        fl.addRow("ODA File Converter (pro DGN):", row)

        box = QGroupBox("Rozsah výkresu (kontrola „Prvek mimo rozsah“)")
        bl = QFormLayout(box)
        self.extent_mode = QComboBox()
        self.extent_mode.addItems(["Nekontrolovat", "Zadaný obdélník", "Území ČR v S-JTSK"])
        r = rules.rozsah
        vals = r if isinstance(r, dict) else {}
        self.ext = {k: _dspin(vals.get(k, 0.0), 3, 1e8, -1e8, 1.0) for k in ("xmin", "ymin", "xmax", "ymax")}
        self.extent_mode.setCurrentIndex(0 if not r else (2 if r == "sjtsk" else 1))
        bl.addRow("Způsob:", self.extent_mode)
        for k, lab in (("xmin", "X min"), ("ymin", "Y min"), ("xmax", "X max"), ("ymax", "Y max")):
            bl.addRow(lab + ":", self.ext[k])
        self.extent_mode.currentIndexChanged.connect(self._extent_mode_changed)
        self._extent_mode_changed()
        fl.addRow(box)
        self.palette = QComboBox()
        self.palette.addItem("MicroStation (čísla z color.tbl)", "microstation")
        self.palette.addItem("AutoCAD (ACI)", "autocad")
        self.palette.setCurrentIndex(max(0, self.palette.findData(rules.paleta)))
        self.palette.setToolTip("Jak číst čísla barev v pravidlech (tabulce od učitele).")
        fl.addRow("Čísla barev v pravidlech:", self.palette)
        self.ms_table = dict(rules.barevna_tabulka)
        row_t = QHBoxLayout()
        self.ms_table_label = QLabel()
        b_tbl = QPushButton("Načíst barevnou tabulku…")
        b_tbl.setToolTip("Barevná tabulka MicroStationu (*.tbl, nebo text „číslo r g b“). Bez ní se "
                         "ověřují jen základní barvy 0–15.")
        b_tbl.clicked.connect(self._load_ms_table)
        b_tbl_clear = QPushButton("Výchozí")
        b_tbl_clear.clicked.connect(self._clear_ms_table)
        row_t.addWidget(self.ms_table_label, 1)
        row_t.addWidget(b_tbl)
        row_t.addWidget(b_tbl_clear)
        fl.addRow("Barevná tabulka MicroStationu:", row_t)
        self._update_ms_label()
        tabs.addTab(gen, "Obecné")

        # --- kontroly po skupinách
        groups: dict[str, QVBoxLayout] = {}
        for cid, cls in REGISTRY.items():
            check = cls()
            if check.skupina not in groups:
                w = QWidget()
                vl = QVBoxLayout(w)
                vl.setAlignment(Qt.AlignTop)
                sa = QScrollArea()
                sa.setWidgetResizable(True)
                sa.setWidget(w)
                tabs.addTab(sa, check.skupina)
                groups[check.skupina] = vl
            cs = self.config.settings(cid)
            gb = QGroupBox(check.nazev)
            gb.setCheckable(True)
            gb.setChecked(cs.zapnuto)
            gl = QFormLayout(gb)
            gl.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            gl.setHorizontalSpacing(14)
            desc = QLabel(check.popis)
            desc.setWordWrap(True)
            desc.setStyleSheet("color: palette(mid);")
            gl.addRow(desc)
            sev = QComboBox()
            for s in Severity:
                sev.addItem(s.value, s)
            sev.setCurrentIndex(list(Severity).index(cs.zavaznost))
            gl.addRow(_lab("Závažnost:"), sev)
            eds = {"_box": gb, "_sev": sev}
            for p in check.parametry:
                val = cs.parametry.get(p.name, p.default)
                if p.type == "bool":
                    ed = QCheckBox()
                    ed.setChecked(bool(val))
                elif p.type == "float":
                    ed = _dspin(val if val is not None else 0.0, 4, 1e9)
                elif p.type == "int":
                    ed = QSpinBox()
                    ed.setRange(0, 1_000_000_000)
                    ed.setValue(int(val or 0))
                else:
                    ed = QLineEdit(", ".join(val) if isinstance(val, list) else str(val or ""))
                if p.help:
                    ed.setToolTip(p.help)
                gl.addRow(_lab(p.label + ":"), ed)
                eds[p.name] = (p, ed)
            groups[check.skupina].addWidget(gb)
            self._editors[cid] = eds

        row = QHBoxLayout()
        b_all = QPushButton("Zapnout vše")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none = QPushButton("Vypnout vše")
        b_none.clicked.connect(lambda: self._set_all(False))
        b_load = QPushButton("Načíst z YAML…")
        b_load.clicked.connect(self._load_yaml)
        b_save = QPushButton("Uložit do YAML…")
        b_save.clicked.connect(self._save_yaml)
        b_def = QPushButton("Výchozí hodnoty")
        b_def.clicked.connect(self._defaults)
        for b in (b_all, b_none, b_def, b_load, b_save):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Použít")
        bb.button(QDialogButtonBox.Cancel).setText("Zrušit")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _update_ms_label(self):
        if self.ms_table:
            sample = ", ".join(f"{i}=#%02X%02X%02X" % self.ms_table[i] for i in sorted(self.ms_table)[:4])
            self.ms_table_label.setText(f"vlastní ({len(self.ms_table)} barev)")
            self.ms_table_label.setToolTip(sample + "…")
        else:
            self.ms_table_label.setText("výchozí (barvy 0–15)")
            self.ms_table_label.setToolTip("")

    def _load_ms_table(self):
        p, _ = QFileDialog.getOpenFileName(self, "Barevná tabulka MicroStationu", "",
                                           "Barevné tabulky (*.tbl *.txt *.csv);;Vše (*)")
        if not p:
            return
        try:
            self.ms_table = load_ms_color_table(p)
        except Exception as exc:
            QMessageBox.warning(self, "Barevná tabulka", f"Tabulku nelze načíst: {exc}")
            return
        self._update_ms_label()

    def _clear_ms_table(self):
        self.ms_table = {}
        self._update_ms_label()

    def _extent_mode_changed(self):
        on = self.extent_mode.currentIndex() == 1
        for w in self.ext.values():
            w.setEnabled(on)

    def _pick_oda(self):
        p, _ = QFileDialog.getOpenFileName(self, "ODAFileConverter.exe", "", "Programy (*.exe);;Vše (*)")
        if p:
            self.oda.setText(p)

    def _set_all(self, on: bool):
        for eds in self._editors.values():
            eds["_box"].setChecked(on)

    def _defaults(self):
        self._apply_config(Config())

    def _apply_config(self, cfg: Config):
        self.tol.setValue(cfg.tolerance)
        self.prec.setValue(cfg.presnost)
        self.radius.setValue(cfg.okruh_textu)
        self.max_issues.setValue(cfg.max_chyb_na_kontrolu)
        self.ignored.setText(", ".join(cfg.ignorovane_hladiny))
        if cfg.oda_cesta:
            self.oda.setText(cfg.oda_cesta)
        for cid, eds in self._editors.items():
            cs = cfg.settings(cid)
            eds["_box"].setChecked(cs.zapnuto)
            eds["_sev"].setCurrentIndex(list(Severity).index(cs.zavaznost))
            for name, val in eds.items():
                if name.startswith("_"):
                    continue
                p, ed = val
                v = cs.parametry.get(name, p.default)
                if isinstance(ed, QCheckBox):
                    ed.setChecked(bool(v))
                elif isinstance(ed, (QDoubleSpinBox, QSpinBox)):
                    ed.setValue(v or 0)
                else:
                    ed.setText(", ".join(v) if isinstance(v, list) else str(v or ""))

    def _load_yaml(self):
        p, _ = QFileDialog.getOpenFileName(self, "Načíst nastavení", "", "YAML (*.yaml *.yml)")
        if not p:
            return
        try:
            self._apply_config(Config.load(p))
        except Exception as exc:
            QMessageBox.warning(self, "Nastavení", f"Soubor nelze načíst: {exc}")

    def _save_yaml(self):
        p, _ = QFileDialog.getSaveFileName(self, "Uložit nastavení", "nastaveni.yaml", "YAML (*.yaml)")
        if p:
            self.result_config().save(p)

    def result_config(self) -> Config:
        cfg = self.config
        cfg.tolerance = self.tol.value()
        cfg.presnost = self.prec.value()
        cfg.okruh_textu = self.radius.value()
        cfg.max_chyb_na_kontrolu = self.max_issues.value()
        cfg.ignorovane_hladiny = [s.strip() for s in self.ignored.text().split(",") if s.strip()]
        cfg.oda_cesta = self.oda.text().strip()
        for cid, eds in self._editors.items():
            cs = cfg.settings(cid)
            cs.zapnuto = eds["_box"].isChecked()
            cs.zavaznost = Severity.parse(eds["_sev"].currentData())  # QComboBox vrací text, ne Severity
            for name, val in eds.items():
                if name.startswith("_"):
                    continue
                p, ed = val
                if isinstance(ed, QCheckBox):
                    cs.parametry[name] = ed.isChecked()
                elif isinstance(ed, (QDoubleSpinBox, QSpinBox)):
                    cs.parametry[name] = ed.value()
                else:
                    cs.parametry[name] = ed.text().strip()
        return cfg

    def apply_rules_settings(self, rules: RuleSet):
        idx = self.extent_mode.currentIndex()
        if idx == 0:
            rules.rozsah = None
        elif idx == 2:
            rules.rozsah = "sjtsk"
        else:
            rules.rozsah = {k: w.value() for k, w in self.ext.items()}
        rules.paleta = self.palette.currentData()
        rules.barevna_tabulka = dict(self.ms_table)
