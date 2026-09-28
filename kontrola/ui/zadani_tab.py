"""Záložka „Zadání“: tabulka atributů, pravidla, náčrty a fotky, vzorový výkres, správa podkladů."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QSlider, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ..checks.base import fmt_num
from ..importer import template as tpl
from ..importer.table import read_table
from ..io.dxf_loader import load_drawing
from ..project import KINDS, Attachment, Project
from ..rules import RuleSet
from .image_viewer import IMAGE_EXT, ImageBrowser, load_pixmap
from .rules_editor import RulesEditor
from .table_import import ImportSummaryDialog, TableImportWizard

TABLE_EXT = {".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".tsv", ".pdf"}
DRAWING_EXT = {".dxf", ".dgn", ".dwg"}


class DropArea(QFrame):
    filesDropped = Signal(list)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(70)
        self.setStyleSheet("DropArea { border: 2px dashed palette(mid); border-radius: 6px; }")
        lay = QVBoxLayout(self)
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lab.setWordWrap(True)
        lay.addWidget(lab)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.filesDropped.emit(files)
        e.acceptProposedAction()


def open_in_system(path: Path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def human_size(n: int) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return str(n)


# =====================================================================================
class TablePage(QWidget):
    def __init__(self, tab: "ZadaniTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        intro = QLabel("<b>Tabulka atributů od učitele</b> (.xlsx, .xls, .csv nebo PDF). Po importu se v průvodci "
                       "přiřadí sloupce (kód, název, hladina, barva, styl čáry, typ geometrie, povinné atributy, "
                       "povolené hodnoty) a z tabulky se vygenerují pravidla kontrol.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        drop = DropArea("Přetáhněte sem tabulku (.xlsx, .xls, .csv, .pdf)")
        drop.filesDropped.connect(lambda fs: [self.import_file(f) for f in fs])
        lay.addWidget(drop)
        row = QHBoxLayout()
        b = QPushButton("Importovat tabulku…")
        b.clicked.connect(self._pick)
        b.setProperty("primarni", True)
        b2 = QPushButton("Znovu otevřít průvodce pro vybranou")
        b2.clicked.connect(self._reimport)
        b3 = QPushButton("Odebrat tabulku a její pravidla")
        b3.setToolTip("Když jste nahráli špatnou tabulku: odebere ji z projektu i s pravidly, která z ní vznikla.")
        b3.clicked.connect(self._remove)
        row.addWidget(b)
        row.addWidget(b2)
        row.addWidget(b3)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(QLabel("Tabulky v projektu:"))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda it: self._reimport())
        lay.addWidget(self.list, 1)
        self.last = QTextBrowser()
        self.last.setMaximumHeight(170)
        lay.addWidget(QLabel("Poslední import:"))
        lay.addWidget(self.last)

    def refresh(self):
        self.list.clear()
        p = self.tab.project
        if p is None:
            return
        meta = p.meta.get("tabulky", {})
        for a in p.attachments("tabulky"):
            info = meta.get(a.rel, {})
            extra = f" – {info.get('souhrn', 'neimportováno')}"
            it = QListWidgetItem(a.name + extra)
            it.setData(Qt.UserRole, a.rel)
            self.list.addItem(it)
        self.last.setHtml(p.meta.get("posledni_import", ""))

    def _pick(self):
        start = QSettings("KontrolaVykresu", "KontrolaVykresu").value("cesty/podklady", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, "Tabulka atributů", start,
                                                "Tabulky (*.xlsx *.xls *.xlsm *.csv *.txt *.pdf);;Vše (*)")
        for f in files:
            QSettings("KontrolaVykresu", "KontrolaVykresu").setValue("cesty/podklady", str(Path(f).parent))
            self.import_file(f)

    def _reimport(self):
        it = self.list.currentItem()
        if it is None:
            QMessageBox.information(self, "Import", "Vyberte tabulku v seznamu.")
            return
        rel = it.data(Qt.UserRole)
        self.run_wizard(rel)

    def _remove(self):
        it = self.list.currentItem()
        if it is None:
            QMessageBox.information(self, "Odebrat tabulku", "Vyberte tabulku v seznamu.")
            return
        rel = it.data(Qt.UserRole)
        p = self.tab.project
        name = Path(rel).name
        n = sum(1 for r in p.rules.pravidla
                if r.zdroj and (r.zdroj == name or r.zdroj.startswith(name + ",")))
        ans = QMessageBox.question(
            self, "Odebrat tabulku",
            f"Odebrat tabulku {name} z projektu?\n\nZ této tabulky vzniklo {n} pravidel.\n"
            "Ano = odebrat tabulku i její pravidla, Ne = odebrat jen tabulku (pravidla zůstanou).",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if ans == QMessageBox.Cancel:
            return
        removed = p.remove_table(rel, with_rules=(ans == QMessageBox.Yes))
        p.meta["posledni_import"] = f"<b>{name}</b> odebrána z projektu, smazáno pravidel: {removed}."
        self.tab.rules_changed()
        self.tab.project_changed()
        self.refresh()

    def import_file(self, path: str):
        if Path(path).suffix.lower() not in TABLE_EXT:
            QMessageBox.warning(self, "Import", f"{Path(path).name}: nepodporovaný formát tabulky.")
            return
        p = self.tab.project
        rel = p.add_attachment("tabulky", path)
        self.tab.project_changed()
        self.run_wizard(rel)

    def run_wizard(self, rel: str):
        p = self.tab.project
        info = p.meta.setdefault("tabulky", {}).get(rel, {})
        mapping = {k: int(v) for k, v in (info.get("mapovani") or {}).items()} or None
        try:
            dlg = TableImportWizard(str(p.root / rel), self, mapping=mapping,
                                    header_row=info.get("hlavicka"), sheet=info.get("list"))
        except Exception as exc:
            QMessageBox.warning(self, "Import tabulky", f"Tabulku nelze přečíst: {exc}")
            return
        if not dlg.exec():
            self.refresh()
            return
        res = dlg.result
        added, replaced = p.rules.merge(res.rules, replace=True)
        p.meta["tabulky"][rel] = {"hlavicka": dlg.header_row(), "mapovani": dlg.mapping(),
                                  "list": dlg.data.sheet, "souhrn": res.summary()}
        html = f"<b>{Path(rel).name}:</b> {res.summary()} Nových {added}, nahrazeno {replaced}."
        if res.errors:
            html += "<br><b>Nezpracované řádky:</b><br>" + "<br>".join(res.errors)
        if res.warnings:
            html += "<br><b>Upozornění:</b><br>" + "<br>".join(res.warnings)
        p.meta["posledni_import"] = html
        self.tab.rules_changed()
        ImportSummaryDialog(res, added, replaced, self).exec()
        self.refresh()


# =====================================================================================
class ImagesPage(QWidget):
    showBeside = Signal()

    def __init__(self, tab: "ZadaniTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        b_add = QPushButton("Přidat obrázky…")
        b_add.clicked.connect(self._pick)
        b_del = QPushButton("Odebrat obrázek")
        b_del.clicked.connect(self._remove)
        b_side = QPushButton("Otevřít vedle výkresu")
        b_side.setToolTip("Zobrazí náčrt v panelu vedle výkresu – panel lze odpojit do plovoucího okna.")
        b_side.clicked.connect(self.showBeside)
        for b in (b_add, b_del, b_side):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        drop = DropArea("Přetáhněte sem náčrty a fotky (JPG, PNG, PDF)")
        drop.setMinimumHeight(50)
        drop.filesDropped.connect(self.add_files)
        lay.addWidget(drop)
        split = QSplitter(Qt.Horizontal)
        self.browser = ImageBrowser()
        self.browser.noteChanged.connect(lambda rel, t: self.tab.note_changed(rel, t))
        self.browser.currentChanged.connect(self._current_changed)
        split.addWidget(self.browser)
        split.addWidget(self._background_box())
        split.setSizes([900, 300])
        lay.addWidget(split, 1)

    def _background_box(self) -> QWidget:
        box = QGroupBox("Podklad pod výkresem (jen vizuálně)")
        fl = QFormLayout(box)
        self.bg_on = QCheckBox("Zobrazit obrázek pod výkresem")
        self.bg_img = QComboBox()
        self.bg_x = QDoubleSpinBox()
        self.bg_y = QDoubleSpinBox()
        for w in (self.bg_x, self.bg_y):
            w.setRange(-1e8, 1e8)
            w.setDecimals(2)
            w.setSuffix(" m")
        self.bg_scale = QDoubleSpinBox()
        self.bg_scale.setRange(0.00001, 1000)
        self.bg_scale.setDecimals(5)
        self.bg_scale.setValue(0.1)
        self.bg_scale.setSuffix(" m/px")
        self.bg_rot = QDoubleSpinBox()
        self.bg_rot.setRange(-360, 360)
        self.bg_rot.setSuffix(" °")
        self.bg_op = QSlider(Qt.Horizontal)
        self.bg_op.setRange(5, 100)
        self.bg_op.setValue(50)
        fl.addRow(self.bg_on)
        fl.addRow("Obrázek:", self.bg_img)
        fl.addRow("X levého dolního rohu:", self.bg_x)
        fl.addRow("Y levého dolního rohu:", self.bg_y)
        fl.addRow("Měřítko:", self.bg_scale)
        fl.addRow("Natočení:", self.bg_rot)
        fl.addRow("Průhlednost:", self.bg_op)
        b_2p = QPushButton("Umístit podle 2 bodů…")
        b_2p.setToolTip("Klikněte na dva body v obrázku a stejné body ve výkresu – posun, měřítko "
                        "a natočení se dopočítají.")
        b_2p.clicked.connect(lambda: self.bg_img.currentData() and self.tab.georefRequested.emit(
            self.bg_img.currentData()))
        fl.addRow(b_2p)
        b_fit = QPushButton("Roztáhnout na rozsah výkresu")
        b_fit.clicked.connect(self._fit_to_drawing)
        fl.addRow(b_fit)
        note = QLabel("Podklad slouží jen k vizuálnímu porovnání, do kontrol nevstupuje.")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        fl.addRow(note)
        for w in (self.bg_x, self.bg_y, self.bg_scale, self.bg_rot):
            w.valueChanged.connect(self._bg_changed)
        self.bg_on.toggled.connect(self._bg_changed)
        self.bg_img.currentIndexChanged.connect(self._bg_changed)
        self.bg_op.valueChanged.connect(self._bg_changed)
        self._bg_loading = False
        return box

    def refresh(self):
        p = self.tab.project
        self.browser.set_project(p)
        self._bg_loading = True
        self.bg_img.clear()
        for rel in self.browser.images():
            self.bg_img.addItem(Path(rel).name, rel)
        vzor = p.meta.get("vzor") if p else None
        if vzor and Path(vzor).suffix.lower() in IMAGE_EXT and (p.root / vzor).is_file():
            self.bg_img.addItem(f"Vzor: {Path(vzor).name}", vzor)
        bg = (p.meta.get("podklad") or {}) if p else {}
        self.bg_on.setChecked(bool(bg.get("zapnuto")))
        self.bg_img.setCurrentIndex(max(0, self.bg_img.findData(bg.get("obrazek"))))
        self.bg_x.setValue(float(bg.get("x", 0.0)))
        self.bg_y.setValue(float(bg.get("y", 0.0)))
        self.bg_scale.setValue(float(bg.get("meritko", 0.1)))
        self.bg_rot.setValue(float(bg.get("rotace", 0.0)))
        self.bg_op.setValue(int(float(bg.get("pruhlednost", 0.5)) * 100))
        self._bg_loading = False

    def _current_changed(self, rel):
        pass

    def _pick(self):
        start = QSettings("KontrolaVykresu", "KontrolaVykresu").value("cesty/podklady", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, "Náčrty a fotky", start,
                                                "Obrázky (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.pdf);;Vše (*)")
        if files:
            QSettings("KontrolaVykresu", "KontrolaVykresu").setValue("cesty/podklady", str(Path(files[0]).parent))
            self.add_files(files)

    def add_files(self, files: list[str]):
        p = self.tab.project
        last = None
        bad = []
        for f in files:
            if Path(f).suffix.lower() not in IMAGE_EXT:
                bad.append(Path(f).name)
                continue
            last = p.add_attachment("obrazky", f)
        if bad:
            QMessageBox.warning(self, "Obrázky", "Nepodporovaný formát: " + ", ".join(bad))
        self.tab.project_changed()
        if last:
            self.browser.show_image(last)

    def _remove(self):
        rel = self.browser.current
        if not rel:
            return
        if QMessageBox.question(self, "Obrázky", f"Odebrat {Path(rel).name} z projektu?") == QMessageBox.Yes:
            self.tab.project.remove_attachment(rel)
            self.tab.project_changed()

    def _fit_to_drawing(self):
        d = self.tab.get_drawing()
        rel = self.bg_img.currentData()
        if d is None or not rel:
            QMessageBox.information(self, "Podklad", "Je potřeba otevřený výkres a vybraný obrázek.")
            return
        b = d.bounds()
        pm = load_pixmap(self.tab.project.root / rel)
        if b is None or pm.isNull():
            return
        self._bg_loading = True
        self.bg_x.setValue(b[0])
        self.bg_y.setValue(b[1])
        self.bg_scale.setValue(max((b[2] - b[0]) / pm.width(), (b[3] - b[1]) / pm.height()))
        self.bg_on.setChecked(True)
        self._bg_loading = False
        self._bg_changed()

    def _bg_changed(self, *_):
        if self._bg_loading or self.tab.project is None:
            return
        bg = {"zapnuto": self.bg_on.isChecked(), "obrazek": self.bg_img.currentData(),
              "x": self.bg_x.value(), "y": self.bg_y.value(), "meritko": self.bg_scale.value(),
              "rotace": self.bg_rot.value(), "pruhlednost": self.bg_op.value() / 100}
        self.tab.project.meta["podklad"] = bg
        self.tab.backgroundChanged.emit(bg)


# =====================================================================================
class ProposalDialog(QDialog):
    def __init__(self, rules, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pravidla navržená ze vzoru")
        self.resize(900, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Zaškrtněte pravidla, která chcete převzít. Kód a název můžete později upravit "
                             "v editoru pravidel."))
        self.table = QTableWidget(len(rules), 8)
        self.table.setHorizontalHeaderLabels(["Převzít", "Kód", "Název", "Typ", "Hladina", "Barva",
                                              "Styl čáry", "Buňka / atributy"])
        self.rules = rules
        for i, r in enumerate(rules):
            cb = QTableWidgetItem()
            cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            cb.setCheckState(Qt.Checked)
            self.table.setItem(i, 0, cb)
            vals = [r.kod, r.nazev, r.geometrie.label if r.geometrie else "", r.hladina or "",
                    "" if r.barva is None else str(r.barva), r.styl_cary or "",
                    (r.blok or "") + (f" ({', '.join(r.povinne_atributy)})" if r.povinne_atributy else "")]
            for c, v in enumerate(vals, start=1):
                self.table.setItem(i, c, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Přidat vybraná pravidla")
        bb.button(QDialogButtonBox.Cancel).setText("Zrušit")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def selected(self):
        out = []
        for i, r in enumerate(self.rules):
            if self.table.item(i, 0).checkState() == Qt.Checked:
                r.kod = self.table.item(i, 1).text().strip() or r.kod
                r.nazev = self.table.item(i, 2).text().strip()
                out.append(r)
        return out


class TemplatePage(QWidget):
    def __init__(self, tab: "ZadaniTab"):
        super().__init__()
        self.tab = tab
        self.info: tpl.TemplateInfo | None = None
        self.pdf_labels: set[str] | None = None
        self._loaded_rel: str | None = None
        lay = QVBoxLayout(self)
        intro = QLabel("<b>Vzor od učitele</b>: <b>DXF/DGN</b> – načtou se hladiny, barvy, styly a buňky, lze z něj "
                       "vytvořit pravidla a porovnat výkres. <b>PDF</b> – porovnají se popisy (čísla parcel, bodů, "
                       "č.p.) a vzor lze vložit pod výkres. <b>JPG/PNG</b> (náčrt, sken) – slouží jako podklad "
                       "pod výkresem k vizuálnímu porovnání.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        drop = DropArea("Přetáhněte sem vzor (.dxf / .dgn / .pdf / .jpg / .png)")
        drop.setMinimumHeight(50)
        drop.filesDropped.connect(lambda fs: self.set_template(fs[0]))
        lay.addWidget(drop)
        row = QHBoxLayout()
        b_load = QPushButton("Načíst vzor…")
        b_load.clicked.connect(self._pick)
        b_rules = QPushButton("Vytvořit pravidla ze vzoru")
        b_rules.clicked.connect(self.make_rules)
        b_cmp = QPushButton("Porovnat s kontrolovaným výkresem")
        b_cmp.clicked.connect(self.compare)
        self.b_bg = QPushButton("Vložit pod výkres…")
        self.b_bg.setToolTip("Zobrazí vzor (PDF/obrázek) průhledně pod výkresem; umístí se podle 2 bodů.")
        self.b_bg.clicked.connect(lambda: self._loaded_rel and self.tab.georefRequested.emit(self._loaded_rel))
        for b in (b_load, b_rules, b_cmp, self.b_bg):
            row.addWidget(b)
        row.addStretch(1)
        self.status = QLabel()
        row.addWidget(self.status)
        lay.addLayout(row)
        split = QSplitter(Qt.Vertical)
        self.layers = QTableWidget(0, 7)
        self.layers.setHorizontalHeaderLabels(["Hladina", "Prvků", "Barvy", "Styly čar", "Tloušťky",
                                               "Typy prvků", "Buňky"])
        self.layers.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.layers.verticalHeader().setVisible(False)
        self.layers.horizontalHeader().setStretchLastSection(True)
        from PySide6.QtWidgets import QStackedWidget
        from .image_viewer import ImageView
        self.stack = QStackedWidget()
        self.preview = ImageView()
        self.stack.addWidget(self.layers)
        self.stack.addWidget(self.preview)
        split.addWidget(self.stack)
        self.diff = QTableWidget(0, 5)
        self.diff.setHorizontalHeaderLabels(["Kategorie", "Položka", "Vzor", "Kontrolovaný výkres", "Rozdíl"])
        self.diff.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.diff.verticalHeader().setVisible(False)
        self.diff.horizontalHeader().setStretchLastSection(True)
        split.addWidget(self.diff)
        lay.addWidget(split, 1)

    def refresh(self):
        p = self.tab.project
        rel = p.meta.get("vzor") if p else None
        if rel and rel != self._loaded_rel and (p.root / rel).is_file():
            self._load(rel)
        elif not rel:
            self.info = None
            self.pdf_labels = None
            self._loaded_rel = None
            self.layers.setRowCount(0)
            self.diff.setRowCount(0)
            self.stack.setCurrentWidget(self.layers)
            self.b_bg.setEnabled(False)
            self.status.setText("Vzor není načten.")

    def _pick(self):
        f, _ = QFileDialog.getOpenFileName(self, "Vzor od učitele", "",
                                           "Vzory (*.dxf *.dgn *.dwg *.pdf *.jpg *.jpeg *.png *.tif *.tiff);;Vše (*)")
        if f:
            self.set_template(f)

    def set_template(self, path: str):
        suf = Path(path).suffix.lower()
        if suf not in DRAWING_EXT and suf not in IMAGE_EXT:
            QMessageBox.warning(self, "Vzor", "Vzor musí být výkres (DXF/DGN), PDF nebo obrázek (JPG/PNG).")
            return
        p = self.tab.project
        old = p.meta.get("vzor")
        rel = p.add_attachment("vzor", path)
        if old and old != rel:
            p.remove_attachment(old)
        p.meta["vzor"] = rel
        self._loaded_rel = None
        self.tab.project_changed()
        self._load(rel)

    def _load(self, rel: str):
        p = self.tab.project
        path = p.root / rel
        self.diff.setRowCount(0)
        if path.suffix.lower() in IMAGE_EXT:
            self.info = None
            self._loaded_rel = rel
            self.preview.set_pixmap(load_pixmap(path))
            self.stack.setCurrentWidget(self.preview)
            self.b_bg.setEnabled(True)
            self.pdf_labels = None
            if path.suffix.lower() == ".pdf":
                try:
                    from ..importer.pdf_vzor import pdf_labels
                    self.pdf_labels = pdf_labels(path)
                except Exception:
                    self.pdf_labels = set()
                if self.pdf_labels:
                    self.status.setText(f"PDF vzor: {Path(rel).name} – {len(self.pdf_labels)} popisů k porovnání")
                else:
                    self.status.setText(f"PDF vzor: {Path(rel).name} – bez textu (sken), jen podklad")
            else:
                self.status.setText(f"Obrázek: {Path(rel).name} – podklad pro vizuální porovnání")
            return
        self.stack.setCurrentWidget(self.layers)
        self.b_bg.setEnabled(False)
        self.pdf_labels = None
        try:
            d = load_drawing(path, None, p.config.oda_cesta or None)
        except Exception as exc:
            QMessageBox.warning(self, "Vzor", f"Vzorový výkres nelze načíst:\n{exc}")
            return
        self.info = tpl.analyze(d)
        self._loaded_rel = rel
        self.status.setText(f"Vzor: {Path(rel).name} – {len(d.features)} prvků, {len(self.info.layers)} hladin")
        self.layers.setRowCount(0)
        for name in sorted(self.info.layers, key=str.lower):
            lu = self.info.layers[name]
            r = self.layers.rowCount()
            self.layers.insertRow(r)
            vals = [name, str(lu.count),
                    ", ".join(f"{c} ({n})" for c, n in lu.colors.most_common()),
                    ", ".join(f"{c} ({n})" for c, n in lu.linetypes.most_common()),
                    ", ".join(f"{fmt_num(c, 2)} mm" for c, _ in lu.lineweights.most_common() if c),
                    ", ".join(f"{g.label} ({n})" for g, n in lu.geoms.most_common()),
                    ", ".join(f"{b} ({n})" for b, n in lu.blocks.most_common())]
            for c, v in enumerate(vals):
                self.layers.setItem(r, c, QTableWidgetItem(v))
        self.layers.resizeColumnsToContents()

    def make_rules(self):
        info = self.info
        if info is None:
            d = self.tab.get_drawing()
            if d is None:
                QMessageBox.information(self, "Vzor", "Nejdřív načtěte vzorový výkres (DXF), nebo otevřete "
                                                      "kontrolovaný výkres.")
                return
            if QMessageBox.question(
                    self, "Vzor",
                    "Pravidla se dají vytvořit jen ze vzoru ve formátu DXF/DGN (PDF ani obrázek neobsahují "
                    "hladiny).\n\nVytvořit návrh pravidel z vašeho kontrolovaného výkresu? Pravidla pak "
                    "projděte a opravte podle PDF/náčrtu – další kontroly už budou hlídat, že se jich "
                    "držíte v celém výkresu.") != QMessageBox.Yes:
                return
            info = tpl.analyze(d)
        proposals = tpl.propose_rules(info, self.tab.project.rules)
        if not proposals:
            QMessageBox.information(self, "Vzor", "Všechny hladiny a buňky vzoru už mají pravidlo.")
            return
        dlg = ProposalDialog(proposals, self)
        if dlg.exec():
            chosen = dlg.selected()
            rs = RuleSet(pravidla=chosen)
            added, replaced = self.tab.project.rules.merge(rs)
            self.tab.rules_changed()
            QMessageBox.information(self, "Vzor", f"Přidáno {added} pravidel ze vzoru.")

    def compare(self):
        d = self.tab.get_drawing()
        if self._loaded_rel and self.info is None:
            if not self.pdf_labels:
                QMessageBox.information(self, "Porovnání", "Obrázek (náčrt, sken) nelze porovnat automaticky. "
                                        "Vložte ho pod výkres tlačítkem „Vložit pod výkres…“ a porovnejte "
                                        "vizuálně.")
                return
            if d is None:
                QMessageBox.information(self, "Vzor", "Není otevřený kontrolovaný výkres.")
                return
            from ..importer.pdf_vzor import compare_labels
            missing, extra = compare_labels(self.pdf_labels, d)
            self.diff.setRowCount(0)
            for lab in missing:
                self._diff_row(["Popis", lab, "ano", "–", "Popis ze vzoru ve výkresu chybí"])
            for lab in extra:
                self._diff_row(["Popis", lab, "–", "ano", "Popis navíc (ve vzoru není)"])
            self.diff.resizeColumnsToContents()
            self.status.setText(f"Popisy: chybí {len(missing)}, navíc {len(extra)} "
                                f"(ze {len(self.pdf_labels)} ve vzoru)")
            return
        if self.info is None:
            QMessageBox.information(self, "Vzor", "Nejdřív načtěte vzor.")
            return
        if d is None:
            QMessageBox.information(self, "Vzor", "Není otevřený kontrolovaný výkres.")
            return
        diffs = tpl.compare(self.info, tpl.analyze(d))
        self.diff.setRowCount(0)
        for x in diffs:
            r = self.diff.rowCount()
            self.diff.insertRow(r)
            for c, v in enumerate([x.kategorie, x.polozka, x.vzor, x.vykres, x.popis]):
                self.diff.setItem(r, c, QTableWidgetItem(v))
        self.diff.resizeColumnsToContents()
        if not diffs:
            QMessageBox.information(self, "Porovnání", "Hladiny, barvy, styly i buňky odpovídají vzoru.")
        else:
            self.status.setText(f"Porovnání: {len(diffs)} rozdílů")

    def _diff_row(self, vals: list[str]):
        r = self.diff.rowCount()
        self.diff.insertRow(r)
        for c, v in enumerate(vals):
            self.diff.setItem(r, c, QTableWidgetItem(v))


# =====================================================================================
class AttachmentsPage(QWidget):
    def __init__(self, tab: "ZadaniTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.proj_label = QLabel()
        self.proj_label.setWordWrap(True)
        top.addWidget(self.proj_label, 1)
        b_ren = QPushButton("Přejmenovat projekt…")
        b_ren.clicked.connect(self._rename)
        b_dir = QPushButton("Otevřít složku projektu")
        b_dir.clicked.connect(lambda: open_in_system(self.tab.project.root))
        top.addWidget(b_ren)
        top.addWidget(b_dir)
        lay.addLayout(top)
        row = QHBoxLayout()
        for text, slot in (("Přidat…", self._add), ("Nahradit…", self._replace), ("Smazat", self._delete),
                           ("Otevřít soubor", self._open)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Druh", "Soubor", "Velikost", "Změněno"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.currentCellChanged.connect(lambda *a: self._preview())
        self.table.cellDoubleClicked.connect(lambda *a: self._open())
        split.addWidget(self.table)
        self.preview = QLabel("Náhled")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumWidth(280)
        self.preview.setWordWrap(True)
        self.preview.setFrameShape(QFrame.StyledPanel)
        split.addWidget(self.preview)
        split.setSizes([700, 380])
        lay.addWidget(split, 1)
        note = QLabel("Všechny soubory jsou uložené ve složce projektu na tomto počítači. Nic se nikam "
                      "neodesílá. Celý projekt uložíte do jednoho souboru přes Soubor → Uložit projekt jako "
                      "(.kontrola).")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        lay.addWidget(note)

    def refresh(self):
        p = self.tab.project
        if p is None:
            return
        src = p.drawing_source or "–"
        self.proj_label.setText(f"<b>Projekt:</b> {p.name}<br><b>Složka:</b> {p.root}<br>"
                                f"<b>Kontrolovaný výkres:</b> {src}")
        self.table.setRowCount(0)
        items = p.attachments()
        cp = p.drawing_copy
        if cp and cp.is_file():
            st = cp.stat()
            items.insert(0, Attachment("vykres", cp.relative_to(p.root).as_posix(), cp, st.st_size,
                                       dt.datetime.fromtimestamp(st.st_mtime)))
        for a in items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            kind = KINDS.get(a.kind, "Kontrolovaný výkres")
            for c, v in enumerate([kind, a.name, human_size(a.size), a.modified.strftime("%d.%m.%Y %H:%M")]):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, a.rel)
                it.setData(Qt.UserRole + 1, a.kind)
                self.table.setItem(r, c, it)
        self._preview()

    def _current(self):
        r = self.table.currentRow()
        if r < 0:
            return None, None
        it = self.table.item(r, 0)
        return it.data(Qt.UserRole), it.data(Qt.UserRole + 1)

    def _preview(self):
        rel, kind = self._current()
        self.preview.setPixmap(QPixmap())
        if not rel:
            self.preview.setText("Vyberte soubor pro náhled.")
            return
        path = self.tab.project.root / rel
        suf = path.suffix.lower()
        if suf in IMAGE_EXT and kind == "obrazky":
            pm = load_pixmap(path)
            if not pm.isNull():
                self.preview.setPixmap(pm.scaled(360, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        if suf in TABLE_EXT:
            try:
                td = read_table(path)
                rows = td.rows[:12]
                html = "<table border=1 cellspacing=0 cellpadding=2 style='font-size:9pt'>" + "".join(
                    "<tr>" + "".join(f"<td>{c[:18]}</td>" for c in r[:6]) + "</tr>" for r in rows) + "</table>"
                self.preview.setText(html)
                return
            except Exception as exc:
                self.preview.setText(f"Náhled nelze zobrazit: {exc}")
                return
        if suf in DRAWING_EXT:
            self.preview.setText(f"Výkres {path.name}\n{human_size(path.stat().st_size)}")
            return
        self.preview.setText(path.name)

    def _add(self):
        kinds = list(KINDS.items())
        label, ok = QInputDialog.getItem(self, "Přidat podklad", "Druh podkladu:", [v for _, v in kinds], 0, False)
        if not ok:
            return
        kind = next(k for k, v in kinds if v == label)
        if kind == "tabulky":
            self.tab.table_page._pick()
        elif kind == "obrazky":
            self.tab.images_page._pick()
        elif kind == "vzor":
            self.tab.template_page._pick()
        else:
            files, _ = QFileDialog.getOpenFileNames(self, "Zadání a dokumenty", "",
                                                    "Dokumenty (*.doc *.docx *.pdf *.odt *.txt *.xls *.xlsx);;Vše (*)")
            for f in files:
                self.tab.project.add_attachment(kind, f)
            if files:
                self.tab.project_changed()
        self.refresh()

    def _replace(self):
        rel, kind = self._current()
        if not rel or kind == "vykres":
            QMessageBox.information(self, "Podklady", "Vyberte podklad (kontrolovaný výkres se mění "
                                                     "tlačítkem Otevřít výkres).")
            return
        f, _ = QFileDialog.getOpenFileName(self, "Nahradit soubor", "", "Vše (*)")
        if not f:
            return
        new_rel = self.tab.project.replace_attachment(rel, f)
        if kind == "tabulky":
            self.tab.project.meta.setdefault("tabulky", {}).pop(rel, None)
            if QMessageBox.question(self, "Podklady", "Tabulka byla nahrazena. Znovu z ní vytvořit pravidla?") \
                    == QMessageBox.Yes:
                self.tab.table_page.run_wizard(new_rel)
        if kind == "vzor":
            self.tab.template_page._loaded_rel = None
        self.tab.project_changed()

    def _delete(self):
        rel, kind = self._current()
        if not rel or kind == "vykres":
            return
        if QMessageBox.question(self, "Podklady", f"Smazat {Path(rel).name} z projektu?") != QMessageBox.Yes:
            return
        self.tab.project.remove_attachment(rel)
        self.tab.project.meta.get("tabulky", {}).pop(rel, None)
        self.tab.project_changed()

    def _open(self):
        rel, _ = self._current()
        if rel:
            open_in_system(self.tab.project.root / rel)

    def _rename(self):
        p = self.tab.project
        name, ok = QInputDialog.getText(self, "Projekt", "Název projektu:", text=p.name)
        if ok and name.strip():
            p.meta["nazev"] = name.strip()
            self.tab.project_changed()


# =====================================================================================
class ZadaniTab(QWidget):
    rulesChanged = Signal()
    projectModified = Signal()
    backgroundChanged = Signal(dict)
    showSketchBeside = Signal()
    noteChangedSignal = Signal(str, str)
    georefRequested = Signal(str)  # rel. cesta obrázku / PDF, který se má umístit pod výkres

    def __init__(self, get_drawing, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.get_drawing = get_drawing
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.tabs = QTabWidget()
        self.table_page = TablePage(self)
        self.rules_editor = RulesEditor()
        self.rules_editor.rulesChanged.connect(self._rules_edited)
        self.rules_editor.showImage.connect(self.show_image)
        self.images_page = ImagesPage(self)
        self.images_page.showBeside.connect(self.showSketchBeside)
        self.template_page = TemplatePage(self)
        self.attachments_page = AttachmentsPage(self)
        self.tabs.addTab(self.table_page, "Tabulka atributů")
        self.tabs.addTab(self.rules_editor, "Pravidla")
        self.tabs.addTab(self.images_page, "Náčrt a fotky")
        self.tabs.addTab(self.template_page, "Vzorový výkres")
        self.tabs.addTab(self.attachments_page, "Podklady")
        lay.addWidget(self.tabs)

    def set_project(self, project: Project):
        self.project = project
        self.rules_editor.set_rules(project.rules)
        self.refresh()

    def refresh(self):
        if self.project is None:
            return
        self.table_page.refresh()
        self.images_page.refresh()
        self.rules_editor.set_images([(rel, Path(rel).name) for rel in self.images_page.browser.images()])
        self.template_page.refresh()
        self.attachments_page.refresh()

    # ---- volání ze stránek
    def project_changed(self):
        self.project.save()
        self.refresh()
        self.projectModified.emit()

    def rules_changed(self):
        self.rules_editor.set_rules(self.project.rules)
        self.project.save()
        self.rulesChanged.emit()

    def _rules_edited(self):
        if self.project is not None:
            self.project.save()
            self.rulesChanged.emit()

    def note_changed(self, rel: str, text: str):
        self.project.save()
        self.noteChangedSignal.emit(rel, text)

    def show_image(self, rel: str):
        self.tabs.setCurrentWidget(self.images_page)
        self.images_page.browser.show_image(rel)

    # ---- přetažení souborů na záložku
    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.handle_files(files)
        e.acceptProposedAction()

    def handle_files(self, files: list[str]):
        imgs = []
        for f in files:
            suf = Path(f).suffix.lower()
            if suf in DRAWING_EXT:
                self.tabs.setCurrentWidget(self.template_page)
                self.template_page.set_template(f)
            elif suf in (".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".tsv"):
                self.tabs.setCurrentWidget(self.table_page)
                self.table_page.import_file(f)
            elif suf == ".pdf":
                if self.tabs.currentWidget() is self.table_page:
                    self.table_page.import_file(f)
                elif self.tabs.currentWidget() is self.images_page:
                    imgs.append(f)
                else:
                    choice = QMessageBox.question(self, "PDF", f"{Path(f).name}\n\nJe to tabulka atributů? "
                                                  "(Ne = náčrt/fotka)")
                    if choice == QMessageBox.Yes:
                        self.table_page.import_file(f)
                    else:
                        imgs.append(f)
            elif suf in IMAGE_EXT:
                imgs.append(f)
            elif suf in (".yaml", ".yml"):
                self.tabs.setCurrentWidget(self.rules_editor)
                self.rules_editor.load_yaml(f)
            elif suf in (".doc", ".docx", ".odt", ".rtf", ".txt", ".zip", ".zap"):
                self.project.add_attachment("dokumenty", f)
                self.project_changed()
                self.tabs.setCurrentWidget(self.attachments_page)
            else:
                QMessageBox.information(self, "Zadání", f"{Path(f).name}: tento typ souboru aplikace neumí použít.\n\n"
                                        "Výkres: DXF (nebo DGN s převodem). Tabulka atributů: xlsx, xls, csv, PDF. "
                                        "Pravidla: YAML. Náčrty a vzory: JPG, PNG, PDF. Zadání: DOC, DOCX, PDF (Podklady → "
                                        "Přidat… → Zadání a dokumenty).")
        if imgs:
            self.tabs.setCurrentWidget(self.images_page)
            self.images_page.add_files(imgs)
