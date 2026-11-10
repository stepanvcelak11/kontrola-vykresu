"""Okna pro modely a listy CAD (jako Models a Sheet v MicroStationu): přehled modelů, nový list s výřezem
kresby a razítkem, arch (papír) pod výkresem."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox,
                               QVBoxLayout)

from ..cad import tisk as T


def _meritko_vychozi(page, papir_mm) -> int:
    rs = page._pravidla()
    if rs is not None and rs.meritko:
        return int(float(rs.meritko))
    ext = page.dok.rozsah() if page.dok is not None else None
    if ext:
        return int(T.automaticke_meritko(ext, papir_mm))
    return 1000


class _Papir:
    """Volba papíru a měřítka (sdílená pro list i arch)."""

    def __init__(self, form: QFormLayout, page, papir: str = "A3"):
        self.page = page
        self.papir = QComboBox()
        self.papir.addItems(list(T.PAPIRY))
        self.papir.setCurrentText(papir)
        self.sirka = QCheckBox("na šířku")
        self.sirka.setChecked(True)
        r = QHBoxLayout()
        r.addWidget(self.papir)
        r.addWidget(self.sirka)
        r.addStretch(1)
        form.addRow("Papír:", r)
        self.meritko = QSpinBox()
        self.meritko.setRange(1, 1_000_000)
        self.meritko.setPrefix("1 : ")
        self.meritko.setValue(_meritko_vychozi(page, self.rozmer()))
        b = QPushButton("Podle kresby")
        b.setToolTip("Nejmenší kulaté měřítko, ve kterém se celá kresba vejde na papír")
        b.clicked.connect(self._auto)
        r2 = QHBoxLayout()
        r2.addWidget(self.meritko)
        r2.addWidget(b)
        r2.addStretch(1)
        form.addRow("Měřítko:", r2)

    def rozmer(self) -> tuple[float, float]:
        return T.rozmer_papiru(self.papir.currentText(), self.sirka.isChecked())

    def _auto(self):
        ext = self.page.dok.rozsah() if self.page.dok is not None else None
        if ext:
            self.meritko.setValue(int(T.automaticke_meritko(ext, self.rozmer())))


class NovyListDialog(QDialog):
    """Nový výkresový list: papír, měřítko, výřez celé kresby a rámeček s razítkem jedním krokem."""

    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Nový list (Sheet)")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("List je papír pro tisk a odevzdání: na něj se vloží výřez kresby z modelu "
                             "v měřítku a razítko."))
        f = QFormLayout()
        n = len(page.dok.doc.layout_names()) if page.dok is not None else 1
        self.nazev = QLineEdit(f"List {n}")
        f.addRow("Název:", self.nazev)
        self.p = _Papir(f, page)
        self.vyrez = QCheckBox("Vložit výřez celé kresby (v měřítku, uprostřed listu)")
        self.vyrez.setChecked(True)
        self.razitko = QCheckBox("Nakreslit rámeček a razítko")
        self.razitko.setChecked(True)
        f.addRow(self.vyrez)
        f.addRow(self.razitko)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Vytvořit list")
        bb.accepted.connect(self.vytvor)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.vysledek = None

    def vytvor(self):
        pg = self.page
        nazev = self.nazev.text().strip()
        if not nazev:
            QMessageBox.information(self, "List", "Zadejte název listu.")
            return
        if nazev in pg.dok.doc.layout_names():
            QMessageBox.information(self, "List", f"List {nazev} už ve výkresu je.")
            return
        ext = pg.dok.rozsah()
        jm = pg.novy_list(nazev, self.p.rozmer())
        if jm is None:
            return
        pw, ph = self.p.rozmer()
        m = self.p.meritko.value()
        if self.vyrez.isChecked() and ext:
            pg.vyrez_celeho_vykresu(m, ext, (pw, ph), razitko=self.razitko.isChecked())
        if self.razitko.isChecked():
            pg.razitko({"Měřítko": f"1:{m}"})
        pg.view.zoom_all()
        self.vysledek = jm
        self.accept()


class ArchDialog(QDialog):
    """Arch (papír) pod modelem – hranice tisku jako v tiskovém dialogu MicroStationu."""

    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Arch – papír pod výkresem")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Arch ukáže, co se vejde na papír v daném měřítku. Pak ho klikem umístíte "
                             "na výkres a vytisknete do PDF (Výkres a tisk → Tisk)."))
        f = QFormLayout()
        a = T.nacti_arch(page.dok.doc) if page.dok is not None else None
        self.p = _Papir(f, page, getattr(a, "nazev", "A3") if a is not None and getattr(a, "nazev", "") in T.PAPIRY
                        else "A3")
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Umístit arch")
        if a is not None:
            b = bb.addButton("Odstranit arch", QDialogButtonBox.DestructiveRole)
            b.clicked.connect(lambda: self._hotovo("smaž"))
        bb.accepted.connect(lambda: self._hotovo(None))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.prikaz = None

    def text(self) -> str:
        return (f"{self.p.papir.currentText()}{'' if self.p.sirka.isChecked() else ' na výšku'} "
                f"1:{self.p.meritko.value()}")

    def _hotovo(self, co):
        self.prikaz = co or self.text()
        self.accept()


class ModelyDialog(QDialog):
    """Modely a listy výkresu (MicroStation: Models): přepnout, nový list, přejmenovat, smazat."""

    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Modely a listy")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Model</b> = kresba ve skutečných souřadnicích. <b>List</b> = papír pro tisk "
                             "s výřezy kresby a razítkem."))
        self.seznam = QListWidget()
        self.seznam.itemDoubleClicked.connect(lambda _it: self.prepnout())
        lay.addWidget(self.seznam, 1)
        r = QHBoxLayout()
        for text, fn in (("Přepnout", self.prepnout), ("Nový list…", self.novy), ("Přejmenovat…", self.prejmenovat),
                         ("Smazat", self.smazat)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r.addWidget(b)
        lay.addLayout(r)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.napln()
        self.resize(420, 320)

    def napln(self):
        self.seznam.clear()
        doc = self.page.dok.doc
        for jm in doc.layout_names_in_taborder():
            self.seznam.addItem(("● " if jm == self.page.prostor.name else "   ") + jm)
        akt = doc.layout_names_in_taborder().index(self.page.prostor.name) \
            if self.page.prostor.name in doc.layout_names_in_taborder() else 0
        self.seznam.setCurrentRow(akt)

    def _vybrany(self) -> str | None:
        it = self.seznam.currentItem()
        return it.text()[3:] if it is not None else None

    def prepnout(self):
        jm = self._vybrany()
        if jm:
            self.page.nastav_model(jm)
            self.page._napln_modely()
            self.napln()

    def novy(self):
        d = NovyListDialog(self.page, self)
        if d.exec():
            self.napln()

    def prejmenovat(self):
        jm = self._vybrany()
        if not jm or jm == "Model":
            QMessageBox.information(self, "Modely", "Model se nepřejmenovává – vyberte list.")
            return
        novy, ok = QInputDialog.getText(self, "Přejmenovat list", "Nový název:", text=jm)
        novy = (novy or "").strip()
        if ok and novy and novy != jm:
            if novy in self.page.dok.doc.layout_names():
                QMessageBox.information(self, "Modely", f"List {novy} už je.")
                return
            self.page.dok.doc.layouts.rename(jm, novy)
            self.page.historie_zmen.zmena += 1
            self.page._napln_modely()
            self.napln()

    def smazat(self):
        jm = self._vybrany()
        if not jm or jm == "Model":
            QMessageBox.information(self, "Modely", "Model se nemaže – vyberte list.")
            return
        if len(self.page.dok.doc.layout_names()) <= 2:
            QMessageBox.information(self, "Modely", "Výkres musí mít aspoň jeden list.")
            return
        if QMessageBox.question(self, "Smazat list", f"Smazat list {jm} i s jeho výřezy a razítkem?") \
                != QMessageBox.Yes:
            return
        if self.page.prostor.name == jm:
            self.page.nastav_model("Model")
        self.page.dok.doc.layouts.delete(jm)
        self.page.historie_zmen.zmena += 1
        self.page._napln_modely()
        self.napln()
