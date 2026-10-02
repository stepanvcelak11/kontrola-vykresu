"""Stránka „Výpočty“: seznam souřadnic (jako v Gromě) – tabulka, import/export, hromadné úpravy, duplicity.

Seznam se ukládá automaticky do projektu (``vypocty/seznam_bodu.json``) po každé změně; každá změna jde
vrátit (Ctrl+Z) a je v historii.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QTableView, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..geodezie.body import Bod, SeznamBodu, klic_cisla
from ..geodezie.formaty import ODDELOVACE, SLOUPCE, Format, dekoduj, nacti_text, rozpoznej, uloz_soubor


def _cesky(bb: QDialogButtonBox, ok: str | None = None) -> None:
    """Česká tlačítka a dost místa pro text."""
    if bb.button(QDialogButtonBox.Cancel):
        bb.button(QDialogButtonBox.Cancel).setText("Zrušit")
    b = bb.button(QDialogButtonBox.Ok)
    if b is not None:
        if ok:
            b.setText(ok)
        b.setMinimumWidth(b.fontMetrics().horizontalAdvance(b.text()) + 40)

COLS = [("cislo", "Číslo bodu"), ("y", "Y"), ("x", "X"), ("z", "Z"), ("kod", "Kód"), ("kvalita", "Kvalita"),
        ("poznamka", "Poznámka")]


class BodyModel(QAbstractTableModel):
    changeFailed = Signal(str)

    def __init__(self, seznam: SeznamBodu, parent=None):
        super().__init__(parent)
        self.seznam = seznam
        self.des_xy = 2
        self.des_z = 2

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.seznam.body)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return len(COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and o == Qt.Horizontal:
            return COLS[s][1]
        return None

    def data(self, idx, role=Qt.DisplayRole):
        b = self.seznam.body[idx.row()]
        key = COLS[idx.column()][0]
        v = getattr(b, key)
        if role == Qt.DisplayRole:
            if key in ("y", "x"):
                return f"{v:.{self.des_xy}f}"
            if key == "z":
                return "" if v is None else f"{v:.{self.des_z}f}"
            return "" if v is None else str(v)
        if role == Qt.EditRole:
            return "" if v is None else (repr(v) if isinstance(v, float) else str(v))
        if role == Qt.UserRole:  # pro řazení
            if key == "cislo":
                return klic_cisla(v)
            return v
        if role == Qt.TextAlignmentRole and key in ("y", "x", "z", "kvalita"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole and key in ("y", "x", "z") and v is not None:
            return f"{v!r} (plná přesnost)"
        return None

    def flags(self, idx):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def setData(self, idx, value, role=Qt.EditRole):  # noqa: N802
        if role != Qt.EditRole:
            return False
        b = self.seznam.body[idx.row()]
        key = COLS[idx.column()][0]
        text = str(value).strip()
        try:
            if key in ("y", "x"):
                v = float(text.replace(",", "."))
            elif key == "z":
                v = float(text.replace(",", ".")) if text else None
            elif key == "kvalita":
                v = int(text) if text else None
                if v is not None and not 1 <= v <= 8:
                    raise ValueError("Kód kvality je 1–8.")
            elif key == "cislo":
                if not text:
                    raise ValueError("Číslo bodu nesmí být prázdné.")
                v = text
            else:
                v = text
            self.seznam.uprav(b.cislo, **{key: v})
        except ValueError as e:
            self.changeFailed.emit(str(e) if str(e) and "could not convert" not in str(e)
                                   else f"„{text}“ není číslo.")
            return False
        self.dataChanged.emit(idx, idx)
        return True

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()


class BodyFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.kod: str | None = None
        self.setSortRole(Qt.UserRole)

    def filterAcceptsRow(self, row, parent):  # noqa: N802
        b = self.sourceModel().seznam.body[row]
        t = self.text.lower()
        if t and t not in b.cislo.lower() and t not in b.kod.lower() and t not in b.poznamka.lower():
            return False
        return self.kod is None or b.kod == self.kod

    def lessThan(self, a, b):  # noqa: N802
        va, vb = a.data(Qt.UserRole), b.data(Qt.UserRole)
        if va is None or vb is None:
            return va is None and vb is not None
        try:
            return va < vb
        except TypeError:
            return str(va) < str(vb)


class ImportDialog(QDialog):
    """Náhled importu: rozpoznaný formát jde upravit (sloupce, oddělovač, desetinná čárka, znaménko…)."""

    def __init__(self, text: str, name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Import seznamu souřadnic – {name}")
        self.resize(860, 600)
        self.text = text
        self.fmt = rozpoznej(text)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Formát se rozpoznal sám – zkontrolujte náhled. Pořadí sloupců, oddělovač a další "
                             "volby jde změnit."))
        row = QHBoxLayout()
        self.cols: list[QComboBox] = []
        for i in range(7):
            c = QComboBox()
            for k, v in SLOUPCE.items():
                c.addItem(v, k)
            row.addWidget(c)
            self.cols.append(c)
        lay.addLayout(row)
        opts = QHBoxLayout()
        self.odd = QComboBox()
        for k, v in ODDELOVACE.items():
            self.odd.addItem(v, k)
        self.carka = QCheckBox("desetinná čárka")
        self.zap = QCheckBox("záporné souřadnice (−Y −X)")
        self.prohod = QCheckBox("nejdřív X, pak Y")
        self.skip = QSpinBox()
        self.skip.setRange(0, 100)
        self.skip.setPrefix("přeskočit řádků: ")
        for w in (QLabel("Oddělovač:"), self.odd, self.carka, self.zap, self.prohod, self.skip):
            opts.addWidget(w)
        opts.addStretch(1)
        lay.addLayout(opts)
        self.prev = QTableWidget(0, 6)
        self.prev.setHorizontalHeaderLabels(["Číslo", "Y", "X", "Z", "Kód", "Kvalita"])
        self.prev.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.prev.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.prev, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.prepsat = QCheckBox("Body se stejným číslem, které už v seznamu jsou, přepsat (jinak se ponechají "
                                 "původní a vypíšou se)")
        lay.addWidget(self.prepsat)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _cesky(bb, "Přidat do seznamu")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._set_from(self.fmt)
        for c in self.cols:
            c.currentIndexChanged.connect(self._update)
        for w in (self.odd,):
            w.currentIndexChanged.connect(self._update)
        for w in (self.carka, self.zap, self.prohod):
            w.toggled.connect(self._update)
        self.skip.valueChanged.connect(self._update)
        self._update()

    def _set_from(self, f: Format):
        for i, c in enumerate(self.cols):
            c.blockSignals(True)
            c.setCurrentIndex(c.findData(f.sloupce[i] if i < len(f.sloupce) else "-"))
            c.blockSignals(False)
        self.odd.setCurrentIndex(max(0, self.odd.findData(f.oddelovac)))
        self.carka.setChecked(f.desetinna_carka)
        self.zap.setChecked(f.zaporne)
        self.prohod.setChecked(f.prohodit_yx)
        self.skip.setValue(f.preskocit)

    def format(self) -> Format:
        sl = [c.currentData() for c in self.cols]
        while sl and sl[-1] == "-":
            sl.pop()
        return Format(sloupce=sl, oddelovac=self.odd.currentData(), desetinna_carka=self.carka.isChecked(),
                      preskocit=self.skip.value(), zaporne=self.zap.isChecked(), prohodit_yx=self.prohod.isChecked())

    def _update(self):
        self.body, self.varovani, _ = nacti_text(self.text, self.format())
        self.prev.setRowCount(min(len(self.body), 200))
        for r, b in enumerate(self.body[:200]):
            for c, v in enumerate((b.cislo, f"{b.y:.3f}", f"{b.x:.3f}", "" if b.z is None else f"{b.z:.3f}",
                                   b.kod, "" if b.kvalita is None else str(b.kvalita))):
                self.prev.setItem(r, c, QTableWidgetItem(v))
        msg = f"Načte se <b>{len(self.body)}</b> bodů."
        if self.varovani:
            msg += (f" <span style='color:#B45309'>{len(self.varovani)} řádků nejde přečíst:</span> "
                    + "; ".join(self.varovani[:4]) + ("…" if len(self.varovani) > 4 else ""))
        sj = [b for b in self.body if not (300_000 < b.y < 950_000 and 900_000 < b.x < 1_350_000)]
        if self.body and len(sj) > len(self.body) / 2:
            msg += (" <span style='color:#B45309'>Souřadnice nevypadají jako S-JTSK – zkontrolujte pořadí "
                    "sloupců, znaménko a „nejdřív X“.</span>")
        self.info.setText(msg)


class HromadneDialog(QDialog):
    def __init__(self, n: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Hromadná úprava – {n} bodů")
        f = QFormLayout(self)
        self.kod = QLineEdit()
        self.kod.setPlaceholderText("(beze změny)")
        self.kvalita = QComboBox()
        self.kvalita.addItem("(beze změny)", None)
        for k in range(1, 9):
            self.kvalita.addItem(str(k), k)
        self.dy, self.dx, self.dz = (QDoubleSpinBox() for _ in range(3))
        for s in (self.dy, self.dx, self.dz):
            s.setRange(-1e7, 1e7)
            s.setDecimals(3)
            s.setSuffix(" m")
        self.predpona = QLineEdit()
        self.predpona.setPlaceholderText("např. 4001 → 13_4001 s předponou „13_“")
        self.pricti = QSpinBox()
        self.pricti.setRange(-10_000_000, 10_000_000)
        f.addRow("Kód:", self.kod)
        f.addRow("Kód kvality:", self.kvalita)
        f.addRow("Posun Y:", self.dy)
        f.addRow("Posun X:", self.dx)
        f.addRow("Posun Z:", self.dz)
        f.addRow("Předpona čísla:", self.predpona)
        f.addRow("Přičíst k číslu:", self.pricti)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _cesky(bb, "Upravit")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def hodnoty(self) -> dict:
        return {"kod": self.kod.text().strip() or None, "kvalita": self.kvalita.currentData(),
                "dy": self.dy.value(), "dx": self.dx.value(), "dz": self.dz.value(),
                "predpona": self.predpona.text().strip() or None, "pricti_k_cislu": self.pricti.value()}


class DuplicityDialog(QDialog):
    """Duplicity: u každé skupiny vyberete, co s ní (nic se neslučuje bez potvrzení)."""

    def __init__(self, seznam: SeznamBodu, tol: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicitní body")
        self.resize(640, 440)
        self.seznam = seznam
        lay = QVBoxLayout(self)
        self.dup = seznam.duplicity(tol)
        lay.addWidget(QLabel(f"Nalezeno {len(self.dup)} skupin (stejné číslo, nebo různá čísla do "
                             f"{tol * 100:g} cm). Zaškrtnuté se sloučí – první bod zůstane, ostatní se smažou "
                             "(jde vrátit Ctrl+Z)."))
        self.lst = QListWidget()
        for d in self.dup:
            it = QListWidgetItem(d.popis())
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.lst.addItem(it)
        lay.addWidget(self.lst, 1)
        self.prumer = QCheckBox("Poloha a výška sloučeného bodu = průměr")
        lay.addWidget(self.prumer)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _cesky(bb, "Sloučit zaškrtnuté")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def proved(self) -> int:
        n = 0
        for i, d in enumerate(self.dup):
            if self.lst.item(i).checkState() == Qt.Checked:
                self.seznam.sluc(d.body[0], d.body[1:], prumerovat=self.prumer.isChecked())
                n += 1
        return n


class VypoctyPage(QWidget):
    changed = Signal()

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.seznam = SeznamBodu()
        from ..geodezie.spojnice import Spojnice
        self.spojnice = Spojnice()
        self._path: Path | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        head = QLabel("<span style='font-size:16pt;font-weight:800'>Výpočty</span>"
                      "&nbsp;&nbsp;<span style='color:gray'>seznam souřadnic projektu</span>")
        lay.addWidget(head)
        from PySide6.QtWidgets import QTabWidget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        lay.addWidget(self.tabs, 1)
        seznam_w = QWidget()
        outer = lay
        lay = QVBoxLayout(seznam_w)
        lay.setContentsMargins(0, 8, 0, 0)
        bar = QHBoxLayout()
        self.b_import = QPushButton("Import…")
        self.b_import.setToolTip("Načíst seznam souřadnic z TXT / CSV (formát se rozpozná, jde upravit)")
        self.b_export = QPushButton("Export…")
        self.b_export.setToolTip("Uložit seznam (nebo vybrané body) do TXT / CSV")
        self.b_add = QPushButton("+ Bod")
        self.b_add.setToolTip("Přidat nový bod")
        self.b_del = QPushButton("Smazat")
        self.b_del.setToolTip("Smazat vybrané body (Delete) – jde vrátit Ctrl+Z")
        self.b_bulk = QPushButton("Hromadně…")
        self.b_bulk.setToolTip("Kód, kvalita, posun, přečíslování vybraných bodů")
        self.b_dup = QPushButton("Duplicity…")
        self.b_dup.setToolTip("Stejná čísla nebo body na stejném místě – bezpečné sloučení")
        self.b_undo = QPushButton("↶ Zpět")
        self.b_redo = QPushButton("↷ Znovu")
        self.b_polar = QPushButton("Polární metoda…")
        self.b_polar.setToolTip("Výpočet ze zápisníku (polární metoda, orientace, kontroly)")
        self.b_qtrig = QPushButton("QTrig…")
        self.b_qtrig.setToolTip("Body a zápisníky z terénní aplikace QTrig (firemní cloud nebo export)")
        for b in (self.b_import, self.b_export, self.b_qtrig, self.b_add, self.b_del, self.b_bulk, self.b_dup, self.b_undo,
                  self.b_redo, self.b_polar):
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        frow = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat číslo, kód, poznámku…")
        self.search.setClearButtonEnabled(True)
        self.kody = QComboBox()
        self.kody.setToolTip("Jen body s tímto kódem")
        self.des = QSpinBox()
        self.des.setRange(0, 6)
        self.des.setPrefix("desetinná místa: ")
        self.des.setToolTip("Jen zobrazení a export – výpočty počítají s plnou přesností")
        self.count = QLabel()
        for w in (self.search, self.kody, self.des, self.count):
            frow.addWidget(w)
        frow.setStretch(0, 1)
        lay.addLayout(frow)
        self.model = BodyModel(self.seznam, self)
        self.proxy = BodyFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        for c, w in enumerate((150, 130, 130, 90, 120, 70)):
            self.table.setColumnWidth(c, w)
        lay.addWidget(self.table, 1)
        self.msg = QLabel()
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        self.tabs.addTab(seznam_w, "Seznam souřadnic")
        from .grafika_bodu import GrafikaBodu
        self.grafika = GrafikaBodu(self)
        self.tabs.addTab(self.grafika, "Grafika")
        self.grafika.vybrano.connect(self._vyber_z_grafiky)
        from .zapisnik_page import ZapisnikPanel
        self.zapisnik = ZapisnikPanel(self)
        self.tabs.addTab(self.zapisnik, "Zápisník")
        from .ulohy import UlohyPanel
        self.ulohy = UlohyPanel(self)
        self.tabs.addTab(self.ulohy, "Úlohy")
        self.tabs.currentChanged.connect(lambda i: self.ulohy._completer_model.setStringList(
            [b.cislo for b in self.seznam.body]))
        lay = outer
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save)
        # signály
        self.b_import.clicked.connect(lambda: self.import_dialog())
        self.b_export.clicked.connect(lambda: self.export_dialog())
        self.b_qtrig.clicked.connect(lambda: self.qtrig_dialog())
        self.b_add.clicked.connect(self.add_point)
        self.b_del.clicked.connect(self.delete_selected)
        self.b_bulk.clicked.connect(self.bulk_dialog)
        self.b_dup.clicked.connect(self.duplicates_dialog)
        self.b_undo.clicked.connect(self.undo)
        self.b_redo.clicked.connect(self.redo)
        self.b_polar.clicked.connect(lambda: getattr(self.win, "show_vypocet", lambda: None)())
        self.search.textChanged.connect(self._filter)
        self.kody.currentIndexChanged.connect(self._filter)
        self.des.valueChanged.connect(self._decimals)
        self.model.changeFailed.connect(lambda m: self.message(m, True))
        self.model.dataChanged.connect(lambda *a: self._after_change())
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence.Delete, self.table, activated=self.delete_selected)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_a: self.grafika.oznac([b.cislo for b in self.selected()]))
        self.des.setValue(2)
        self._refresh()

    # ------------------------------------------------------------ projekt / ukládání
    def set_project(self, project) -> None:
        self._save_timer.stop()
        self._path = Path(project.root) / "vypocty" / "seznam_bodu.json" if project is not None else None
        try:
            self.seznam = SeznamBodu.nacti(self._path) if self._path else SeznamBodu()
        except (OSError, ValueError, TypeError) as e:
            self.seznam = SeznamBodu()
            self.message(f"Seznam bodů projektu nejde načíst ({e}) – začíná se prázdný, původní soubor zůstal.",
                         True)
            self._path = self._path.with_name("seznam_bodu_obnoveny.json") if self._path else None
        self.model.seznam = self.seznam
        from ..geodezie.spojnice import Spojnice
        self.spojnice = Spojnice.nacti(self._path.with_name("spojnice.json")) if self._path else Spojnice()
        self._refresh()

    def uloz_spojnice(self) -> None:
        self.grafika.pohled.viewport().update()
        if self._path is None:
            return
        try:
            self.spojnice.uloz(self._path.with_name("spojnice.json"))
        except OSError as e:
            self.message(f"Spojnice nejde uložit: {e}", True)

    def protokol_append(self, radky: list[str]) -> None:
        """Každý výpočet se připíše do protokolu projektu (vypocty/protokol.txt) – nic se neztratí."""
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path.with_name("protokol.txt"), "a", encoding="utf-8") as fh:
                fh.write("\n".join(radky) + "\n\n")
        except OSError as e:
            self.message(f"Protokol nejde zapsat: {e}", True)

    def save(self) -> None:
        if self._path is None:
            return
        try:
            self.seznam.uloz(self._path)
        except OSError as e:
            self.message(f"Seznam nejde uložit: {e}", True)

    def _after_change(self):
        self._save_timer.start()  # automatické uložení
        self._refresh(keep=True)
        self.changed.emit()

    # ------------------------------------------------------------ zobrazení
    def _refresh(self, keep: bool = False):
        # „keep“ (jen přepočítat zobrazení) smí být jen při stejném počtu bodů – jinak by tabulka
        # sahala na řádky, které už neexistují (pád Qt); po přidání / smazání vždy úplné obnovení
        n = len(self.seznam.body)
        if not keep or n != getattr(self, "_pocet_radku", n):
            self.model.refresh()
        else:
            self.model.layoutChanged.emit()
        self._pocet_radku = n
        cur = self.kody.currentData()
        self.kody.blockSignals(True)
        self.kody.clear()
        self.kody.addItem("Všechny kódy", None)
        for k in self.seznam.kody():
            self.kody.addItem(k, k)
        i = self.kody.findData(cur)
        self.kody.setCurrentIndex(max(0, i))
        self.kody.blockSignals(False)
        self._filter()
        self.b_undo.setEnabled(self.seznam.lze_zpet())
        self.b_redo.setEnabled(self.seznam.lze_znovu())
        if hasattr(self, "grafika") and self.grafika.isVisible():
            self.grafika.obnov()

    def _filter(self):
        self.proxy.text = self.search.text().strip()
        self.proxy.kod = self.kody.currentData()
        self.proxy.invalidate()
        n, m = self.proxy.rowCount(), len(self.seznam)
        self.count.setText(f"{m} bodů" if n == m else f"{n} z {m} bodů")

    def _decimals(self, d: int):
        self.model.des_xy = self.model.des_z = d
        self.model.layoutChanged.emit()

    def message(self, text: str, warn: bool = False):
        col = "#B45309" if warn else "gray"
        self.msg.setText(f"<span style='color:{col}'>{text}</span>")

    def _vyber_z_grafiky(self, cisla: list[str]):
        """Body vybrané v grafice → vybrat i v tabulce."""
        from PySide6.QtCore import QItemSelection, QItemSelectionModel
        sm = self.table.selectionModel()
        sel = QItemSelection()
        for c in cisla:
            r = next((i for i, b in enumerate(self.seznam.body) if b.cislo == c), None)
            if r is None:
                continue
            idx = self.proxy.mapFromSource(self.model.index(r, 0))
            if idx.isValid():
                sel.select(idx, idx)
        sm.select(sel, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def selected(self) -> list[Bod]:
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return [self.seznam.body[r] for r in sorted(rows) if r < len(self.seznam.body)]

    # ------------------------------------------------------------ akce
    def undo(self):
        if self.seznam.zpet():
            self.message("Vráceno zpět: " + (self.seznam.historie[-2].popis if len(self.seznam.historie) > 1
                                             else ""))
            self._after_change()
            self.model.refresh()

    def redo(self):
        if self.seznam.znovu():
            self.message("Znovu provedeno.")
            self._after_change()
            self.model.refresh()

    def add_point(self):
        n = 1
        cisla = {b.cislo for b in self.seznam.body}
        num = [int(c) for c in cisla if c.isdigit()]
        n = (max(num) + 1) if num else 1
        while str(n) in cisla:
            n += 1
        ref = self.selected()[0] if self.selected() else (self.seznam.body[-1] if self.seznam.body else None)
        b = Bod(str(n), ref.y if ref else 0.0, ref.x if ref else 0.0)
        self.seznam.pridej([b], f"Nový bod {n}")
        self.model.refresh()
        self._after_change()
        src = self.model.index(len(self.seznam.body) - 1, 1)
        idx = self.proxy.mapFromSource(src)
        self.table.setCurrentIndex(idx)
        self.table.edit(idx)

    def delete_selected(self):
        sel = self.selected()
        if not sel:
            self.message("Nejdřív vyberte body v tabulce.", True)
            return
        n = self.seznam.smaz([b.cislo for b in sel])
        self.model.refresh()
        self._after_change()
        self.message(f"Smazáno {n} bodů (vrátit: Ctrl+Z).")

    def import_dialog(self, path: str | None = None, accept: bool = False):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Import seznamu souřadnic", "",
                                                  "Seznam souřadnic (*.txt *.csv *.xyz *.dat *.crd *.ss);;Vše (*)")
        if not path:
            return None
        try:
            text = dekoduj(Path(path).read_bytes())
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import", str(e))
            return None
        dlg = ImportDialog(text, Path(path).name, self)
        if not accept and dlg.exec() != QDialog.Accepted:
            return None
        if not dlg.body:
            QMessageBox.warning(self, "Import", "V souboru nejsou žádné body (zkontrolujte formát).")
            return None
        n, konf = self.seznam.pridej(dlg.body, f"Import {Path(path).name}", prepsat=dlg.prepsat.isChecked())
        self.model.refresh()
        self._after_change()
        msg = f"Přidáno {n} bodů ze souboru {Path(path).name}."
        if konf:
            msg += (f" {len(konf)} čísel už v seznamu bylo a ponechala se původní: " + ", ".join(konf[:12])
                    + ("…" if len(konf) > 12 else ""))
        if dlg.varovani:
            msg += f" Přeskočeno {len(dlg.varovani)} nečitelných řádků."
        self.message(msg, bool(konf or dlg.varovani))
        return n

    def qtrig_dialog(self, klient=None):
        """Okno QTrig (nemodální – může hlídat zakázku, zatímco se pracuje dál)."""
        from .qtrig_dialog import QTrigDialog
        d = getattr(self, "_qtrig", None)
        if d is None or klient is not None:
            d = self._qtrig = QTrigDialog(self, klient)
        d.show()
        d.raise_()
        return d

    def export_dialog(self, path: str | None = None):
        body = self.selected() or [self.seznam.body[self.proxy.mapToSource(self.proxy.index(r, 0)).row()]
                                   for r in range(self.proxy.rowCount())]
        if not body:
            self.message("Seznam je prázdný.", True)
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Export seznamu souřadnic", "seznam.txt",
                                                  "Text – sloupce (*.txt);;CSV pro Excel (*.csv);;"
                                                  "DXF – body, čísla, výšky a spojnice (*.dxf);;"
                                                  "KML – mapy, Google Earth (*.kml);;GeoJSON – QGIS (*.geojson);;"
                                                  "PDF – seznam k tisku a odevzdání (*.pdf)")
        if not path:
            return None
        pripona = Path(path).suffix.lower()
        if pripona == ".pdf":
            from ..geodezie.formaty import zapis_text
            from ..geodezie.protokol import protokol_pdf
            sl = ["cislo", "y", "x", "z"] + (["kod"] if any(b.kod for b in body) else [])
            d = self.des.value()
            pr = getattr(self.win, "project", None)
            nazev = f"Seznam souřadnic {getattr(pr, 'name', '') if pr is not None else ''}".strip()
            text = (f"SEZNAM SOUŘADNIC – S-JTSK, Bpv\npočet bodů: {len(body)}\n\n"
                    + zapis_text(body, sloupce=sl, des_xy=d, des_z=d, hlavicka=True))
            try:
                protokol_pdf(text, path, nazev=nazev)
            except OSError as e:
                QMessageBox.warning(self, "Export", str(e))
                return None
            self.message(f"Seznam {len(body)} bodů uložen do PDF {path}.")
            return path
        if pripona in (".dxf", ".kml", ".geojson", ".json"):
            from ..geodezie import export_mapy as E
            cisla = {b.cislo for b in body}
            spoj = [(a, b) for a, b in self.spojnice.platne(self.seznam) if a.cislo in cisla and b.cislo in cisla]
            try:
                if pripona == ".dxf":
                    E.do_dxf(path, body, spoj, des_z=self.des.value())
                elif pripona == ".kml":
                    E.do_kml(path, body, spoj, Path(path).stem)
                else:
                    E.do_geojson(path, body, spoj)
            except OSError as e:
                QMessageBox.warning(self, "Export", str(e))
                return None
            self.message(f"Uloženo {len(body)} bodů" + (f" a {len(spoj)} spojnic" if spoj else "") + f" do {path}.")
            return path
        sloupce = ["cislo", "y", "x", "z"] + (["kod"] if any(b.kod for b in body) else []) + \
                  (["kvalita"] if any(b.kvalita for b in body) else [])
        d = self.des.value()
        try:
            uloz_soubor(path, body, sloupce=sloupce, des_xy=d, des_z=d)
        except OSError as e:
            QMessageBox.warning(self, "Export", str(e))
            return None
        self.message(f"Uloženo {len(body)} bodů do {path}.")
        return path

    def bulk_dialog(self, values: dict | None = None):
        sel = self.selected()
        if not sel:
            self.message("Vyberte body, které chcete upravit (Ctrl/Shift + klik).", True)
            return
        if values is None:
            dlg = HromadneDialog(len(sel), self)
            if dlg.exec() != QDialog.Accepted:
                return
            values = dlg.hodnoty()
        try:
            n = self.seznam.hromadne([b.cislo for b in sel], **values)
        except ValueError as e:
            QMessageBox.warning(self, "Hromadná úprava", str(e))
            return
        self.model.refresh()
        self._after_change()
        self.message(f"Upraveno {n} bodů (vrátit: Ctrl+Z).")

    def duplicates_dialog(self, tol: float = 0.01, accept_all: bool = False):
        dlg = DuplicityDialog(self.seznam, tol, self)
        if not dlg.dup:
            self.message("Žádné duplicity – každé číslo je jednou a žádné dva body nejsou na stejném místě.")
            return 0
        if accept_all:
            for i in range(dlg.lst.count()):
                dlg.lst.item(i).setCheckState(Qt.Checked)
        elif dlg.exec() != QDialog.Accepted:
            return 0
        n = dlg.proved()
        self.model.refresh()
        self._after_change()
        self.message(f"Sloučeno {n} skupin (vrátit: Ctrl+Z).")
        return n
