"""Editor pravidel (tabulka), načtení a uložení YAML."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .flow import RadekTlacitek
from ..model import GeomType
from ..rules import (Rule, RuleSet, TextRule, norm_style, parse_allowed_values, parse_color,
                     parse_weight, split_list)

COLS = ["Kód", "Název", "Geometrie", "Vrstva", "Barva", "Styl čáry", "Tloušťka", "Buňka",
        "Povinné atributy", "Povolené hodnoty", "Popis (vrstva)", "Popis povinný", "Obrázek",
        "Poznámka", "Zdroj"]
C_KOD, C_NAZEV, C_GEOM, C_HL, C_BARVA, C_STYL, C_TL, C_BLOK, C_ATTR, C_VALS, C_THL, C_TPOV, C_IMG, C_POZN, C_ZDROJ = range(15)

GEOM_CHOICES = [("", None), ("bod", GeomType.BOD), ("linie", GeomType.LINIE), ("polygon", GeomType.POLYGON),
                ("text", GeomType.TEXT)]


def allowed_to_text(d: dict[str, list[str]]) -> str:
    return "; ".join(f"{k}={', '.join(v)}" for k, v in d.items())


class RulesEditor(QWidget):
    rulesChanged = Signal()
    showImage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = RuleSet()
        self.images: list[tuple[str, str]] = []  # (rel, název)
        self._loading = False
        lay = QVBoxLayout(self)
        row = RadekTlacitek()  # v úzkém okně se zalomí
        for text, slot in (("Přidat pravidlo", self.add_rule), ("Smazat vybraná", self.delete_selected),
                           ("Smazat všechna", self.delete_all),
                           ("Načíst YAML…", self.load_yaml), ("Uložit do YAML…", self.save_yaml),
                           ("Zobrazit obrázek", self._show_image)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        self.count = QLabel()
        row.addWidget(self.count)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Vrstvy povolené i bez kódu (rám, pomocné…):"))
        self.extra_layers = QLineEdit()
        self.extra_layers.setPlaceholderText("např. RAM, POPIS_*")
        self.extra_layers.editingFinished.connect(self._sync)
        row2.addWidget(self.extra_layers, 1)
        lay.addLayout(row2)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSortingEnabled(False)
        widths = [70, 220, 100, 190, 70, 110, 90, 110, 140, 220, 130, 110, 120, 170, 200]
        for c, w in enumerate(widths):
            self.table.setColumnWidth(c, w)
        from .theme import fit_headers
        fit_headers(self.table)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._sync)
        lay.addWidget(self.table, 1)
        hint = QLabel("Změny se ukládají do projektu automaticky. Barva: číslo barvy MicroStationu (nebo ACI "
                      "podle Nastavení kontrol), název nebo #RRGGBB. Vrstva smí obsahovat * (např. POPIS_*). "
                      "Povolené hodnoty: DRUH=lípa, dub; MATERIAL=zděná")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        lay.addWidget(hint)

    # ------------------------------------------------------------ data
    def set_images(self, images: list[tuple[str, str]]):
        self.images = images
        for r in range(self.table.rowCount()):
            cb = self.table.cellWidget(r, C_IMG)
            if isinstance(cb, QComboBox):
                cur = cb.currentData()
                self._fill_img_combo(cb, cur)

    def _fill_img_combo(self, cb: QComboBox, current: str | None):
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("", None)
        for rel, name in self.images:
            cb.addItem(name, rel)
        idx = cb.findData(current)
        if idx < 0 and current:
            cb.addItem(current + " (chybí)", current)
            idx = cb.count() - 1
        cb.setCurrentIndex(max(0, idx))
        cb.blockSignals(False)

    def set_rules(self, rules: RuleSet):
        self.rules = rules
        self._loading = True
        self.table.setRowCount(0)
        for r in rules.pravidla:
            self._append_row(r)
        self.extra_layers.setText(", ".join(rules.povolene_hladiny))
        self._loading = False
        self._update_count()

    def _append_row(self, r: Rule):
        row = self.table.rowCount()
        self.table.insertRow(row)
        vals = {
            C_KOD: r.kod, C_NAZEV: r.nazev, C_HL: r.hladina or "",
            C_BARVA: "" if r.barva is None else str(r.barva), C_STYL: r.styl_cary or "",
            C_TL: "" if r.tloustka is None else str(r.tloustka).replace(".", ","),
            C_BLOK: r.blok or "", C_ATTR: ", ".join(r.povinne_atributy),
            C_VALS: allowed_to_text(r.povolene_hodnoty),
            C_THL: (r.text.hladina or "") if r.text else "", C_POZN: r.poznamka or "", C_ZDROJ: r.zdroj or "",
        }
        for c, v in vals.items():
            it = QTableWidgetItem(v)
            if c == C_ZDROJ:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, c, it)
        geom = QComboBox()
        for label, g in GEOM_CHOICES:
            geom.addItem(label, g)
        geom.setCurrentIndex(max(0, geom.findData(r.geometrie)))
        geom.currentIndexChanged.connect(self._sync)
        self.table.setCellWidget(row, C_GEOM, geom)
        tp = QCheckBox()
        tp.setChecked(bool(r.text and r.text.povinny))
        tp.toggled.connect(self._sync)
        self.table.setCellWidget(row, C_TPOV, tp)
        img = QComboBox()
        self._fill_img_combo(img, r.obrazek)
        img.currentIndexChanged.connect(self._sync)
        self.table.setCellWidget(row, C_IMG, img)

    def _text(self, row: int, col: int) -> str:
        it = self.table.item(row, col)
        return it.text().strip() if it else ""

    def _row_rule(self, row: int) -> Rule | None:
        kod = self._text(row, C_KOD)
        if not kod:
            return None
        attrs = [a.upper() for a in split_list(self._text(row, C_ATTR))]
        thl = self._text(row, C_THL)
        tp = self.table.cellWidget(row, C_TPOV)
        tl_v = parse_weight(self._text(row, C_TL))
        old = next((r for r in self.rules.pravidla if r.kod == kod), None)
        text_rule = None
        if thl or (tp is not None and tp.isChecked()):
            text_rule = TextRule(povinny=bool(tp and tp.isChecked()), hladina=thl or None,
                                 atribut=old.text.atribut if old and old.text else None,
                                 uvnitr=old.text.uvnitr if old and old.text else True)
        return Rule(
            kod=kod, nazev=self._text(row, C_NAZEV),
            geometrie=GeomType.parse(self.table.cellWidget(row, C_GEOM).currentData()),  # QComboBox vrací text
            hladina=self._text(row, C_HL) or None, barva=parse_color(self._text(row, C_BARVA)),
            styl_cary=norm_style(self._text(row, C_STYL)), tloustka=tl_v,
            blok=self._text(row, C_BLOK) or None, povinne_atributy=attrs,
            povolene_hodnoty=parse_allowed_values(self._text(row, C_VALS), attrs[0] if attrs else None),
            text=text_rule, obrazek=self.table.cellWidget(row, C_IMG).currentData(),
            poznamka=self._text(row, C_POZN) or None, zdroj=self._text(row, C_ZDROJ) or None,
            # pole, která tabulka editoru nezobrazuje, se převezmou z původního pravidla
            typy_prvku=list(old.typy_prvku) if old else [],
            vyska_textu=old.vyska_textu if old else None, sirka_textu=old.sirka_textu if old else None,
            font=old.font if old else None, zarovnani=old.zarovnani if old else None,
            tucne=old.tucne if old else None, kurziva=old.kurziva if old else None,
            meritko_stylu=old.meritko_stylu if old else None, meritko_bunky=old.meritko_bunky if old else None,
            topologie=old.topologie if old else True,
        )

    def _sync(self, *_):
        if self._loading:
            return
        rules = []
        for row in range(self.table.rowCount()):
            r = self._row_rule(row)
            if r is not None:
                rules.append(r)
        self.rules.pravidla[:] = rules
        self.rules.povolene_hladiny[:] = split_list(self.extra_layers.text())
        self._update_count()
        self.rulesChanged.emit()

    def _update_count(self):
        self.count.setText(f"Pravidel: {len(self.rules.pravidla)}")

    # ------------------------------------------------------------ akce
    def add_rule(self):
        self._loading = True
        n = len(self.rules.pravidla) + 1
        self._append_row(Rule(kod=f"NOVY{n}", zdroj="ručně"))
        self._loading = False
        self.table.scrollToBottom()
        self.table.editItem(self.table.item(self.table.rowCount() - 1, C_KOD))
        self._sync()

    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        if QMessageBox.question(self, "Pravidla", f"Smazat {len(rows)} pravidel?") != QMessageBox.Yes:
            return
        for r in rows:
            self.table.removeRow(r)
        self._sync()

    def delete_all(self):
        if not self.rules.pravidla:
            return
        if QMessageBox.question(self, "Pravidla", f"Smazat všech {len(self.rules.pravidla)} pravidel? "
                                "(Např. po načtení špatného zadání.)") != QMessageBox.Yes:
            return
        self.rules.pravidla.clear()
        self.rules.povolene_hladiny.clear()
        self.rules.meritko = None
        self.set_rules(self.rules)
        self.rulesChanged.emit()

    def load_yaml(self, p: str | None = None):
        if not p:
            p, _ = QFileDialog.getOpenFileName(self, "Načíst pravidla", "", "YAML (*.yaml *.yml)")
        if not p:
            return
        try:
            rs = RuleSet.load(p)
        except Exception as exc:
            QMessageBox.warning(self, "Pravidla", f"Soubor nelze načíst: {exc}")
            return
        replace = QMessageBox.question(
            self, "Pravidla", f"Soubor obsahuje {len(rs.pravidla)} pravidel.\n\n"
            "Ano = nahradit současná pravidla, Ne = přidat (sloučit podle kódu).",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if replace == QMessageBox.Cancel:
            return
        if replace == QMessageBox.Yes:
            self.rules.pravidla[:] = rs.pravidla
            self.rules.povolene_hladiny[:] = rs.povolene_hladiny
            self.rules.paleta = rs.paleta
            self.rules.meritko = rs.meritko
            if rs.mapa_tloustek:
                self.rules.mapa_tloustek = dict(rs.mapa_tloustek)
            if rs.barevna_tabulka:
                self.rules.barevna_tabulka = rs.barevna_tabulka
            if rs.rozsah:
                self.rules.rozsah = rs.rozsah
        else:
            self.rules.merge(rs)
        self.set_rules(self.rules)
        self.rulesChanged.emit()

    def save_yaml(self):
        p, _ = QFileDialog.getSaveFileName(self, "Uložit pravidla", "pravidla.yaml", "YAML (*.yaml)")
        if p:
            self.rules.save(p, header="Pravidla kontrol atributů (Kontrola výkresu)")

    def _show_image(self):
        row = self.table.currentRow()
        if row < 0:
            return
        rel = self.table.cellWidget(row, C_IMG).currentData()
        if rel:
            self.showImage.emit(rel)
        else:
            QMessageBox.information(self, "Pravidla", "K pravidlu není připojen obrázek (sloupec Obrázek).")
