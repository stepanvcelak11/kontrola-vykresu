"""Další seznam souřadnic vedle aktivního (jako víc otevřených souborů .crd v Gromě).

Do výpočetních oken z něj jde body přetahovat, výpočty je najdou i podle čísla (hledání ve všech otevřených
seznamech) a body jde přenášet mezi ním a aktivním seznamem. Ukládá se do projektu (vypocty/seznamy/<název>.json),
takže se příště dá znovu otevřít."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QTableView, QVBoxLayout, QWidget)

from ..geodezie.body import SeznamBodu


class DalsiSeznam(QWidget):
    def __init__(self, page, nazev: str, seznam: SeznamBodu | None = None, cesta: Path | None = None):
        super().__init__()
        from .vypocty_page import BodyFilter, BodyModel
        self.page = page
        self.nazev = nazev
        self.cesta = cesta
        self.seznam = seznam or SeznamBodu()
        self.setProperty("kompaktni", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)
        from .flow import RadekTlacitek
        r = RadekTlacitek()
        self.b_do = QPushButton("→ Do aktivního")
        self.b_do.setToolTip("Označené body (nic neoznačeno = všechny) zkopírovat do aktivního seznamu")
        self.b_z = QPushButton("← Z aktivního")
        self.b_z.setToolTip("Body označené v aktivním seznamu zkopírovat sem")
        self.b_imp = QPushButton("Import…")
        self.b_exp = QPushButton("Export…")
        self.b_akt = QPushButton("Nastavit jako aktivní")
        self.b_akt.setToolTip("Prohodit: tento seznam bude aktivní (do něj se ukládají výpočty)")
        for b in (self.b_do, self.b_z, self.b_imp, self.b_exp, self.b_akt):
            r.addWidget(b)
        self.pocet = QLabel()
        r.addWidget(self.pocet)
        lay.addLayout(r)
        self.model = BodyModel(self.seznam, self)
        self.proxy = BodyFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for c, w in enumerate((150, 120, 120, 80, 100, 60)):
            self.table.setColumnWidth(c, w)
        lay.addWidget(self.table, 1)
        self.b_do.clicked.connect(lambda: self.do_aktivniho())
        self.b_z.clicked.connect(lambda: self.z_aktivniho())
        self.b_imp.clicked.connect(lambda: self.importuj())
        self.b_exp.clicked.connect(lambda: self.exportuj())
        self.b_akt.clicked.connect(lambda: self.nastav_aktivni())
        self.model.dataChanged.connect(lambda *_a: self.uloz())
        self.obnov()

    # ------------------------------------------------------------
    def obnov(self):
        self.model.refresh()
        self.pocet.setText(f"{len(self.seznam.body)} bodů")

    def uloz(self):
        if self.cesta is not None:
            try:
                self.cesta.parent.mkdir(parents=True, exist_ok=True)
                self.seznam.uloz(self.cesta)
            except OSError:
                pass

    def vybrane(self):
        rows = sorted({self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()})
        return [self.seznam.body[r] for r in rows] or list(self.seznam.body)

    def do_aktivniho(self) -> int:
        body = self.vybrane()
        if not body:
            return 0
        n, konf = self.page.seznam.pridej(list(body), f"Ze seznamu {self.nazev}")
        self.page.model.refresh()
        self.page._after_change()
        self.page.message(f"Do aktivního seznamu přidáno {n} bodů ze seznamu {self.nazev}."
                          + (f" {len(konf)} čísel už tam bylo (ponechána původní)." if konf else ""), bool(konf))
        return n

    def z_aktivniho(self) -> int:
        body = self.page.selected()
        if not body:
            self.page.message("V aktivním seznamu označte body, které chcete přenést.", True)
            return 0
        n, _k = self.seznam.pridej(list(body), "Z aktivního seznamu")
        self.obnov()
        self.uloz()
        return n

    def importuj(self, path: str | None = None, accept: bool = False) -> int:
        from ..geodezie.formaty import dekoduj
        from .vypocty_page import ImportDialog
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Import do seznamu", "",
                                                  "Seznam souřadnic (*.txt *.csv *.xyz *.dat *.crd *.ss);;Vše (*)")
        if not path:
            return 0
        try:
            text = dekoduj(Path(path).read_bytes())
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import", str(e))
            return 0
        dlg = ImportDialog(text, Path(path).name, self)
        if not accept and dlg.exec() != ImportDialog.Accepted:
            return 0
        n, _k = self.seznam.pridej(dlg.body, f"Import {Path(path).name}")
        self.obnov()
        self.uloz()
        return n

    def exportuj(self, path: str | None = None) -> bool:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Export seznamu", f"{self.nazev}.txt", "Text (*.txt)")
        if not path:
            return False
        radky = [" ".join([b.cislo, f"{b.y:.3f}", f"{b.x:.3f}"] + ([f"{b.z:.3f}"] if b.z is not None else [])
                          + ([b.kod] if b.kod else [])) for b in self.seznam.body]
        Path(path).write_text("\n".join(radky) + "\n", encoding="utf-8")
        return True

    def nastav_aktivni(self):
        """Prohodí obsah s aktivním seznamem (výpočty se pak ukládají sem)."""
        p = self.page
        a, b = list(p.seznam.body), list(self.seznam.body)
        p.seznam.zmen("Prohození s dalším seznamem", lambda body: (body.clear(), body.extend(b), len(b))[-1], len(b))
        self.seznam.body[:] = a
        p.model.refresh()
        p._after_change()
        self.obnov()
        self.uloz()


def bezpecny_nazev(t: str) -> str:
    return re.sub(r"[^\w\- ]+", "_", t.strip())[:60] or "seznam"


def otevri_dalsi(page, nazev: str | None = None, prazdny: bool = False):
    """Otevře další seznam souřadnic v datových oknech; název = soubor v projektu (vypocty/seznamy)."""
    if nazev is None:
        from PySide6.QtWidgets import QInputDialog
        ulozene = ulozene_seznamy(page)
        nazev, ok = QInputDialog.getItem(page, "Další seznam souřadnic", "Název seznamu (nový nebo uložený):",
                                         ulozene or [f"Seznam {len(page.dalsi_seznamy) + 2}"], 0, True)
        if not ok or not nazev.strip():
            return None
    nazev = bezpecny_nazev(nazev)
    for w in page.dalsi_seznamy:
        if w.nazev == nazev:
            page.tabs.otevri(w)
            return w
    root = getattr(page, "_root", None)
    cesta = Path(root) / "vypocty" / "seznamy" / f"{nazev}.json" if root is not None else None
    seznam = None
    if cesta is not None and cesta.exists() and not prazdny:
        try:
            seznam = SeznamBodu.nacti(cesta)
        except (OSError, ValueError, TypeError):
            seznam = None
    w = DalsiSeznam(page, nazev, seznam, cesta)
    page.dalsi_seznamy.append(w)
    page.tabs.addTab(w, f"Seznam souřadnic – {nazev}")
    sub = page.tabs.okno(w)
    if sub is not None:
        sub.resize(520, 340)
    page.tabs.otevri(w)
    return w


def ulozene_seznamy(page) -> list[str]:
    root = getattr(page, "_root", None)
    d = Path(root) / "vypocty" / "seznamy" if root is not None else None
    return sorted(p.stem for p in d.glob("*.json")) if d is not None and d.is_dir() else []
