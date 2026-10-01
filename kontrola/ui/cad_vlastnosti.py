"""Vlastnosti prvku CAD (jako „Informace o prvku“ v MicroStationu): zobrazit a upravit."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox,
                               QVBoxLayout)

from ..cad import symbologie as S
from ..cad import upravy as U


def vlastnosti_ms(prvek, rs, znama_barva: int | None = None):
    """Vlastnosti prvku s barvou, stylem a tloušťkou pojmenovanými jako v MicroStationu."""
    out = []
    for k, popis, v in U.vlastnosti(prvek):
        if k == "layer":
            out.append((k, "Hladina", v))
        elif k == "color":
            b = znama_barva if znama_barva is not None and v != 256 else S.aci_na_ms(v, rs)
            popis = "Barva (0–255, prázdné = dle hladiny)" + ("" if znama_barva is not None or v == 256 else
                                                               " – odhad z DXF")
            out.append(("ms_barva", popis, "" if b is None else str(b)))
        elif k == "linetype":
            out.append(("ms_styl", "Styl čáry (0–7 nebo kód, např. 2.103)", S.typ_na_styl(v)))
        elif k == "lineweight":
            w = S.lw_na_wt(v, rs)
            out.append(("ms_tl", "Tloušťka wt (0–31, prázdné = dle hladiny)", "" if w is None else str(w)))
        else:
            out.append((k, popis, v))
    return out


def preved_ms(z: dict, rs) -> dict:
    """Změny v pojmech MicroStationu → atributy DXF."""
    out = {}
    for k, v in z.items():
        t = str(v).strip()
        if k == "ms_barva":
            out["color"] = 256 if t in ("", "dle hladiny") else S.ms_na_aci(int(t), rs)
        elif k == "ms_styl":
            out["linetype"] = "BYLAYER" if t in ("", "dle hladiny") else S.styl_na_typ(t)
        elif k == "ms_tl":
            out["lineweight"] = -1 if t in ("", "dle hladiny") else S.wt_na_lw(int(t), rs)[0]
        else:
            out[k] = v
    return out


def _f(v) -> str:
    return f"{v:.3f}" if isinstance(v, float) else str(v)


class VlastnostiDialog(QDialog):
    def __init__(self, page, prvek, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.prvek = prvek
        sj = page.sjtsk and page._je_model()
        self.setWindowTitle(f"Vlastnosti – {U.NAZVY_TYPU.get(prvek.dxftype(), prvek.dxftype())}")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.pole: dict[str, QLineEdit | QCheckBox] = {}
        self._puvodni: dict[str, str] = {}
        self.rs = page._pravidla()
        self.znama = page.kresleni.ms_barvy_prvku.get(prvek.dxf.handle) if page.kresleni else None
        for k, popis, v in vlastnosti_ms(prvek, self.rs, self.znama):
            if k.startswith("_"):
                form.addRow(popis + ":", QLabel(_f(v)))
                continue
            if isinstance(v, bool):
                w = QCheckBox()
                w.setChecked(v)
            else:
                if isinstance(v, tuple):
                    x, y = v
                    txt = f"{-x:.3f} {-y:.3f}" if sj else f"{x:.3f} {y:.3f}"
                    popis += " (Y X)" if sj else " (x y)"
                else:
                    txt = _f(v) if not isinstance(v, float) else f"{v:.6g}"
                w = QLineEdit(txt)
                self._puvodni[k] = txt
            form.addRow(popis + ":", w)
            self.pole[k] = w
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Použít")
        bb.accepted.connect(self.pouzit)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.sj = sj
        self.vysledek = None

    def zmeny(self) -> dict:
        out = {}
        typy = {k: v for k, _p, v in vlastnosti_ms(self.prvek, self.rs, self.znama)}
        for k, w in self.pole.items():
            if isinstance(w, QCheckBox):
                if w.isChecked() != typy[k]:
                    out[k] = w.isChecked()
                continue
            t = w.text().strip()
            if t == self._puvodni.get(k):
                continue
            puv = typy[k]
            if isinstance(puv, tuple):
                c = t.replace(",", " ").replace(";", " ").split()
                if len(c) != 2:
                    raise ValueError(f"{k}: zadejte dvě souřadnice.")
                a, b = float(c[0]), float(c[1])
                out[k] = (-a, -b) if self.sj else (a, b)
            elif isinstance(puv, bool):
                out[k] = t.lower() in ("ano", "1", "true")
            elif isinstance(puv, int):
                out[k] = int(t)
            elif isinstance(puv, float):
                out[k] = float(t.replace(",", "."))
            else:
                out[k] = t
        return out

    def pouzit(self):
        try:
            z = preved_ms(self.zmeny(), self.rs)
            if "linetype" in z and z["linetype"].startswith("DGN Style"):
                S.zajisti_styly(self.page.dok.doc)
            if z:
                pg = self.page
                novy = U.nastav_vlastnosti(pg.prostor, pg.historie_zmen, self.prvek, z)
                zb = self.zmeny().get("ms_barva", self.znama)
                if zb not in (None, "") and pg.kresleni is not None:
                    pg.kresleni.ms_barvy_prvku[novy.dxf.handle] = int(zb)
                pg._po_zmene([novy], [self.prvek])
                pg.vyber = [novy]
                pg._zvyrazni()
                pg.vypis(f"Vlastnosti změněny: {', '.join(z)}")
                self.vysledek = novy
        except (ValueError, KeyError) as e:
            QMessageBox.warning(self, "Vlastnosti", f"Hodnotu nejde použít: {e}")
            return
        self.accept()
