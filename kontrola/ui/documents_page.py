"""Stránka „Pokyny ze zadání“: Word/PDF od učitele – text, požadavky, vrstvy → pravidla, tabulky."""

from __future__ import annotations

import csv
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from ..importer.dokument import DOC_EXT, document_settings, layer_rules, looks_like_rules_table, read_document, requirements


def doc_rule_source(name: str, zdroj: str | None) -> bool:
    return bool(zdroj) and zdroj.startswith(name + " (")


class DocumentsPage(QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.doc = None
        self.rules = []
        lay = QVBoxLayout(self)
        intro = QLabel("<b>Pokyny ze zadání</b> – Word (DOC, DOCX), ODT, RTF nebo PDF od učitele. Aplikace z něj "
                       "vytáhne požadavky (měřítko, písmo, vrstvy, pokyny „musí / nesmí“) a popisy vrstev "
                       "převede na pravidla kontroly. Soubor přetáhněte sem nebo kamkoli do záložky Zadání.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QHBoxLayout()
        b_add = QPushButton("Přidat dokument…")
        b_add.setProperty("primarni", True)
        b_add.clicked.connect(self._pick)
        self.b_rules = QPushButton("Přidat vrstvy do pravidel")
        self.b_rules.setToolTip("Popisy vrstev z dokumentu (např. „Vrstva 58 – podrobné body… Barva 0…“) "
                                "se přidají k pravidlům ze Směrnice.")
        self.b_rules.clicked.connect(self.add_rules)
        self.b_table = QPushButton("Importovat tabulku z dokumentu…")
        self.b_table.clicked.connect(self._import_table)
        b_open = QPushButton("Otevřít ve Wordu")
        b_open.clicked.connect(self._open)
        b_del = QPushButton("Odebrat")
        b_del.clicked.connect(self._remove)
        for b in (b_add, self.b_rules, self.b_table, b_open, b_del):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.setMaximumWidth(260)
        self.list.currentItemChanged.connect(lambda *_: self._load())
        split.addWidget(self.list)
        right = QSplitter(Qt.Vertical)
        g1 = QGroupBox("Požadavky a pokyny nalezené v dokumentu")
        l1 = QVBoxLayout(g1)
        srow = QHBoxLayout()
        self.settings_info = QLabel()
        self.settings_info.setWordWrap(True)
        self.settings_info.setTextFormat(Qt.RichText)
        srow.addWidget(self.settings_info, 1)
        self.b_apply = QPushButton("Použít v nastavení")
        self.b_apply.setToolTip("Toleranci ze zadání nastaví pro kontrolu (nedotažení, body blízko…).")
        self.b_apply.clicked.connect(self.apply_settings)
        srow.addWidget(self.b_apply)
        l1.addLayout(srow)
        self.req = QTableWidget(0, 3)
        self.req.setHorizontalHeaderLabels(["Co", "Hodnota", "Věta ze zadání"])
        self.req.verticalHeader().setVisible(False)
        self.req.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.req.setWordWrap(True)
        self.req.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.req.setColumnWidth(0, 130)
        self.req.setColumnWidth(1, 120)
        l1.addWidget(self.req)
        right.addWidget(g1)
        g2 = QGroupBox("Vrstvy popsané v dokumentu (lze přidat do pravidel)")
        l2 = QVBoxLayout(g2)
        self.lay_table = QTableWidget(0, 6)
        self.lay_table.setHorizontalHeaderLabels(["Vrstva", "Název", "Prvek", "Barva", "Tloušťka", "Písmo / výška"])
        self.lay_table.verticalHeader().setVisible(False)
        self.lay_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.lay_table.horizontalHeader()
        hh.setStretchLastSection(True)
        for c, wdt in enumerate((70, 300, 80, 70, 80)):
            self.lay_table.setColumnWidth(c, wdt)
        l2.addWidget(self.lay_table)
        self.rules_state = QLabel()
        self.rules_state.setWordWrap(True)
        l2.addWidget(self.rules_state)
        right.addWidget(g2)
        g3 = QGroupBox("Celý text")
        l3 = QVBoxLayout(g3)
        self.text = QTextBrowser()
        l3.addWidget(self.text)
        right.addWidget(g3)
        right.setSizes([220, 170, 260])
        split.addWidget(right)
        split.setSizes([240, 900])
        lay.addWidget(split, 1)

    # ------------------------------------------------------------ seznam
    def refresh(self):
        p = self.tab.project
        cur = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.list.blockSignals(True)
        self.list.clear()
        if p is not None:
            for a in p.attachments("dokumenty"):
                if Path(a.name).suffix.lower() in DOC_EXT:
                    it = QListWidgetItem(a.name)
                    it.setData(Qt.UserRole, a.rel)
                    self.list.addItem(it)
        self.list.blockSignals(False)
        self.select(cur)

    def select(self, rel: str | None):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == rel:
                self.list.setCurrentRow(i)
                return
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._load()

    def _load(self):
        it = self.list.currentItem()
        self.doc, self.rules = None, []
        self.req.setRowCount(0)
        self.lay_table.setRowCount(0)
        if it is None:
            self.text.setHtml("<p style='color:#6B7280'>Zatím žádný dokument. Přidejte zadání od učitele "
                              "(Word nebo PDF).</p>")
            self.rules_state.clear()
            self.settings_info.clear()
            self.b_apply.hide()
            self._buttons()
            return
        path = self.tab.project.root / it.data(Qt.UserRole)
        try:
            self.doc = read_document(path)
        except Exception as exc:  # noqa: BLE001 – poškozený / nepodporovaný soubor
            self.text.setHtml(f"<p>Dokument nelze přečíst: {escape(str(exc))}</p>")
            self._buttons()
            return
        reqs = requirements(self.doc)
        self.req.setRowCount(len(reqs))
        for r, q in enumerate(reqs):
            for c, v in enumerate((q.druh, q.hodnota, q.veta)):
                self.req.setItem(r, c, QTableWidgetItem(v))
        self.req.resizeRowsToContents()
        self.rules = layer_rules(self.doc, self.tab.project.rules.meritko)
        self.lay_table.setRowCount(len(self.rules))
        for r, rule in enumerate(self.rules):
            unit = "mm" if self.tab.project.rules.meritko else "m"
            font = ", ".join(x for x in (rule.font or "", f"výška {rule.vyska_textu:g} {unit}" if rule.vyska_textu
                                         else "", rule.zarovnani or "") if x)
            vals = (rule.hladina, rule.nazev, rule.geometrie.label if rule.geometrie else "–",
                    "" if rule.barva is None else str(rule.barva),
                    "" if rule.tloustka is None else f"{rule.tloustka:g}", font)
            for c, v in enumerate(vals):
                self.lay_table.setItem(r, c, QTableWidgetItem(v))
        self._show_settings()
        html = "".join(f"<p>{escape(p)}</p>" for p in self.doc.odstavce)
        self.text.setHtml(html or "<p>(dokument neobsahuje text)</p>")
        self._update_state()
        self._buttons()

    def _show_settings(self):
        """Hodnoty ze zadání porovnané s projektem: měřítko, písmo, tolerance, formát."""
        p = self.tab.project
        self.found = document_settings(self.doc) if self.doc else {}
        ok, bad = "<span style='color:#16A34A'>✓</span>", "<span style='color:#B45309'>⚠</span>"
        parts = []
        sc = self.found.get("meritko")
        if sc:
            m = p.rules.meritko
            parts.append(f"měřítko 1:{sc} " + (ok if m == sc else
                         f"{bad} pravidla počítají písmo v 1:{m}" if m else "(pravidla ho neurčují)"))
        font = self.found.get("pismo")
        if font:
            used = any(r.font and font.lower() in r.font.lower() for r in p.rules.pravidla)
            parts.append(f"písmo {escape(font)} " + (ok if used else f"{bad} v pravidlech není"))
        tol = self.found.get("tolerance")
        if tol:
            cur = p.config.tolerance
            parts.append(f"tolerance {tol[0] * 1000:g} mm " + (ok if abs(cur - tol[0]) < 1e-9 else
                         f"{bad} v nastavení je {cur * 1000:g} mm"))
        if self.found.get("format"):
            parts.append(f"odevzdat jako {escape(self.found['format'])}")
        self.settings_info.setText("<b>Pro kontrolu:</b> " + " · ".join(parts) if parts else
                                   "<span style='color:#6B7280'>Měřítko, písmo ani toleranci dokument "
                                   "neuvádí.</span>")
        self.b_apply.setVisible(bool(tol) and abs(p.config.tolerance - tol[0]) >= 1e-9)

    def apply_settings(self):
        tol = getattr(self, "found", {}).get("tolerance")
        if not tol:
            return
        p = self.tab.project
        if QMessageBox.question(self, "Použít v nastavení",
                                f"Zadání uvádí: „{tol[1]}“\n\nNastavit toleranci kontroly na {tol[0] * 1000:g} mm "
                                f"(teď {p.config.tolerance * 1000:g} mm)?") != QMessageBox.Yes:
            return
        p.config.tolerance = tol[0]
        self.tab.project_changed()
        self.tab.rulesChanged.emit()
        self._show_settings()

    def _present(self) -> list:
        name = self.doc.path.name if self.doc else ""
        return [r for r in self.tab.project.rules.pravidla if doc_rule_source(name, r.zdroj)]

    def _update_state(self):
        if not self.rules:
            self.rules_state.setText("V dokumentu nejsou popsané vrstvy s atributy (nebo je nejde přečíst).")
            return
        n = len(self._present())
        self.rules_state.setText(
            f"<span style='color:#16A34A'>✓ Vrstvy z dokumentu jsou v pravidlech ({n}).</span>" if n else
            f"<span style='color:#B45309'>{len(self.rules)} vrstev zatím není v pravidlech – bez nich se jejich "
            "prvky hlásí jako „vrstva není ve Směrnici“.</span>")

    def _buttons(self):
        self.b_rules.setEnabled(bool(self.rules))
        self.b_table.setEnabled(bool(self.doc and any(looks_like_rules_table(t) for t in self.doc.tabulky)))

    # ------------------------------------------------------------ akce
    def add_file(self, path: str, ask: bool = True):
        rel = self.tab.project.add_attachment("dokumenty", path)
        self.tab.project_changed()
        self.select(rel)
        if ask and self.rules and not self._present():
            layers = ", ".join(r.hladina for r in self.rules)
            if QMessageBox.question(self, "Pokyny ze zadání",
                                    f"V dokumentu {Path(path).name} jsou popsané vrstvy {layers} (barva, tloušťka, "
                                    "písmo…). Přidat je do pravidel kontroly?") == QMessageBox.Yes:
                self.add_rules()
        return rel

    def add_rules(self):
        if not self.rules:
            return
        p = self.tab.project
        from ..rules import RuleSet
        added, replaced = p.rules.merge(RuleSet(pravidla=list(self.rules)), replace=True)
        p.meta["posledni_import"] = (f"<b>{self.doc.path.name}:</b> vrstvy z dokumentu – nových {added}, "
                                     f"nahrazeno {replaced}.")
        self.tab.rules_changed()
        self.tab.project_changed()
        self._update_state()

    def _pick(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Zadání od učitele", "",
                                                "Dokumenty (*.doc *.docx *.odt *.rtf *.pdf *.txt);;Vše (*)")
        for f in files:
            self.add_file(f)

    def _import_table(self):
        if not self.doc:
            return
        tables = [t for t in self.doc.tabulky if looks_like_rules_table(t)]
        if not tables:
            return
        t = max(tables, key=len)
        out = self.tab.project.root / "podklady" / "tabulky" / f"{self.doc.path.stem}_tabulka.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8-sig") as fh:
            csv.writer(fh, delimiter=";").writerows(t)
        self.tab.tabs.setCurrentWidget(self.tab.table_page)
        self.tab.table_page.import_file(str(out))

    def _open(self):
        it = self.list.currentItem()
        if it is not None:
            from .zadani_tab import open_in_system
            open_in_system(self.tab.project.root / it.data(Qt.UserRole))

    def _remove(self):
        it = self.list.currentItem()
        if it is None:
            return
        rel = it.data(Qt.UserRole)
        name = Path(rel).name
        p = self.tab.project
        n = sum(1 for r in p.rules.pravidla if doc_rule_source(name, r.zdroj))
        msg = f"Odebrat {name} z projektu?"
        if n:
            msg += f"\n\nZ dokumentu vzniklo {n} pravidel – odeberou se také."
        if QMessageBox.question(self, "Odebrat dokument", msg) != QMessageBox.Yes:
            return
        p.remove_attachment(rel)
        if n:
            p.rules.pravidla = [r for r in p.rules.pravidla if not doc_rule_source(name, r.zdroj)]
            self.tab.rules_changed()
        self.tab.project_changed()
