"""Okno „Kontrola výpočtu souřadnic“: zápisník + dané body → výpočet → porovnání se seznamem studenta."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ..checks.seznam import read_point_list
from ..vypocet import compare, compute, diagnose, read_zap, text_report
from .theme import fit_headers


class VypocetDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Kontrola výpočtu souřadnic (zápisník z totální stanice)")
        self.resize(1000, 720)
        self.report = ""
        lay = QVBoxLayout(self)
        intro = QLabel("Program sám spočítá souřadnice podrobných bodů ze zápisníku (polární metoda stejně jako "
                       "Groma: dvě polohy dalekohledu, vodorovná délka × měřítkový koeficient, orientační posun "
                       "vážený délkami, výšky od nivelačního bodu) a porovná je s vaším seznamem souřadnic.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        meta = project.meta.setdefault("vypocet", {}) if project else {}
        self.zap = self._file_row(form, "Zápisník (.zap):", meta.get("zapisnik", ""),
                                  "Zápisník (*.zap *.txt *.gsi);;Leica GSI (*.gsi);;Vše (*)")
        self.dane = self._file_row(form, "Dané body (Y X Z):", meta.get("dane", ""),
                                   "Seznam (*.txt *.crd *.csv);;Vše (*)", multi=True,
                                   tip="Stanoviska (např. gnss_husovice.txt) a orientační / nivelační body "
                                       "z ČÚZK. Více souborů oddělte středníkem.")
        default_seznam = meta.get("seznam", "")
        if not default_seznam and project is not None:
            s = project.attachments("seznamy")
            default_seznam = str(s[0].path) if s else ""
        self.seznam = self._file_row(form, "Váš seznam souřadnic:", default_seznam,
                                     "Seznam (*.txt *.crd *.csv);;Vše (*)")
        krow = QHBoxLayout()
        self.k_auto = QCheckBox("spočítat (Křovák + nadmořská výška)")
        self.k_auto.setChecked(meta.get("koeficient") in (None, ""))
        self.k = QDoubleSpinBox()
        self.k.setDecimals(10)
        self.k.setRange(0.99, 1.01)
        self.k.setSingleStep(0.000001)
        self.k.setValue(float(meta.get("koeficient") or 0.9999))
        self.k.setEnabled(not self.k_auto.isChecked())
        self.k_auto.toggled.connect(lambda on: self.k.setEnabled(not on))
        krow.addWidget(self.k_auto)
        krow.addWidget(self.k)
        krow.addWidget(QLabel("(nebo opište z protokolu Gromy – „Měřítkový koeficient“)"))
        krow.addStretch(1)
        form.addRow("Měřítkový koeficient:", krow)
        trow = QHBoxLayout()
        self.tol_xy = QDoubleSpinBox()
        self.tol_xy.setDecimals(3)
        self.tol_xy.setRange(0.001, 1.0)
        self.tol_xy.setValue(float(meta.get("tol_xy", 0.01)))
        self.tol_xy.setSuffix(" m")
        self.tol_z = QDoubleSpinBox()
        self.tol_z.setDecimals(3)
        self.tol_z.setRange(0.001, 1.0)
        self.tol_z.setValue(float(meta.get("tol_z", 0.01)))
        self.tol_z.setSuffix(" m")
        trow.addWidget(QLabel("poloha"))
        trow.addWidget(self.tol_xy)
        trow.addWidget(QLabel("výška"))
        trow.addWidget(self.tol_z)
        trow.addStretch(1)
        form.addRow("Povolený rozdíl:", trow)
        lay.addLayout(form)

        brow = QHBoxLayout()
        self.b_run = QPushButton("Spočítat a porovnat")
        self.b_run.setProperty("primarni", True)
        self.b_run.setDefault(True)
        self.b_run.clicked.connect(self.run)
        self.b_save = QPushButton("Uložit protokol…")
        self.b_save.clicked.connect(self.save_report)
        self.b_save.setEnabled(False)
        self.b_coords = QPushButton("Uložit vypočtené souřadnice…")
        self.b_coords.clicked.connect(self.save_coords)
        self.b_coords.setEnabled(False)
        self.b_prot = QPushButton("Výpočetní protokol…")
        self.b_prot.setToolTip("Celý protokol výpočtu (import, redukce, orientace, podrobné body, kontroly, "
                               "seznam) do TXT nebo PDF")
        self.b_prot.clicked.connect(lambda: self.save_protokol())
        self.b_prot.setEnabled(False)
        self.b_list = QPushButton("Do seznamu bodů")
        self.b_list.setToolTip("Vypočtené body přidat do seznamu souřadnic na stránce Výpočty")
        self.b_list.clicked.connect(self.to_list)
        self.b_list.setEnabled(False)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        for b in (self.b_run, self.b_prot, self.b_list, self.b_save, self.b_coords):
            brow.addWidget(b)
        brow.addWidget(self.summary, 1)
        lay.addLayout(brow)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Bod", "Stanovisko", "dY [m]", "dX [m]", "dZ [m]", "Výsledek",
                                              "Vypočteno Y X Z"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        for c, w in enumerate((150, 110, 80, 80, 80, 220)):
            self.table.setColumnWidth(c, w)
        fit_headers(self.table)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, "Porovnání bodů")
        self.diag = QTextBrowser()
        self.tabs.addTab(self.diag, "Diagnóza – proč se liší")
        self.kt = QTableWidget(0, 5)
        self.kt.setHorizontalHeaderLabels(["Kontrola", "Stanovisko", "Bod", "Hodnota", "Vysvětlení"])
        self.kt.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.kt.verticalHeader().setVisible(False)
        self.kt.horizontalHeader().setStretchLastSection(True)
        for c, w in enumerate((150, 110, 150, 150)):
            self.kt.setColumnWidth(c, w)
        self.tabs.addTab(self.kt, "Kontrola měření")
        self.plot = DeviationPlot()
        self.tabs.addTab(self.plot, "Mapa odchylek")
        self.log = QTextBrowser()
        self.tabs.addTab(self.log, "Postup výpočtu")
        lay.addWidget(self.tabs, 4)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.accept)
        crow = QHBoxLayout()
        crow.addStretch(1)
        crow.addWidget(close)
        lay.addLayout(crow)
        self.result = None

    def _file_row(self, form, label, value, filt, multi=False, tip=""):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        ed = QLineEdit(value)
        if tip:
            ed.setToolTip(tip)
        b = QPushButton("Vybrat…")
        b.setAutoDefault(False)

        def pick():
            if multi:
                fs, _ = QFileDialog.getOpenFileNames(self, label, "", filt)
                if fs:
                    ed.setText("; ".join(fs))
            else:
                f, _ = QFileDialog.getOpenFileName(self, label, "", filt)
                if f:
                    ed.setText(f)
        b.clicked.connect(pick)
        h.addWidget(ed, 1)
        h.addWidget(b)
        form.addRow(label, w)
        return ed

    def _nacti_mereni(self, zap: str, known) -> list:
        """Zápisník Gromy (.zap) nebo Leica GSI-8/16 (orientace = dané body na začátku stanoviska)."""
        from ..geodezie.gsi import je_gsi, read_gsi, rozdel_orientace
        text = Path(zap).read_bytes()[:4000].decode("cp1250", errors="replace")
        self._gsi_zpravy = []
        if not je_gsi(text):
            return read_zap(zap)
        stations, var = read_gsi(zap)
        rozdel_orientace(stations, {p.cislo for p in known})
        self._gsi_zpravy = [f"GSI: stanovisko {st.bod} – orientace na " + (", ".join(o.bod for o in st.orient)
                                                                           or "žádný daný bod")
                            for st in stations] + var[:10]
        return stations

    def run(self):
        zap = self.zap.text().strip()
        dane = [s.strip() for s in self.dane.text().split(";") if s.strip()]
        seznam = self.seznam.text().strip()
        missing = [n for n, v in (("zápisník", zap), ("dané body", dane)) if not v]
        if missing:
            QMessageBox.information(self, "Kontrola výpočtu", "Vyberte: " + ", ".join(missing) + ".")
            return
        try:
            known = [p for f in dane for p in read_point_list(f)]
            stations = self._nacti_mereni(zap, known)
            student = read_point_list(seznam) if seznam else []
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Kontrola výpočtu", f"Soubor nelze načíst: {exc}")
            return
        if not stations:
            QMessageBox.warning(self, "Kontrola výpočtu", "V zápisníku nejsou žádná stanoviska "
                                "(očekává se formát Gromy: „1 <stanovisko> <výška přístroje> *“).")
            return
        k = None if self.k_auto.isChecked() else self.k.value()
        res = compute(stations, known, k)
        bad, rows = (compare(res, student, self.tol_xy.value(), self.tol_z.value(), known=known) if student
                     else ([], []))
        self.result = res
        self._stations, self._known, self._files = stations, known, (zap, "; ".join(dane))
        diag = self._gsi_zpravy + diagnose(res, rows, self.tol_xy.value(), self.tol_z.value())
        self.report = text_report(res, rows, bad, diag)
        self._fill_checks(res, diag)
        self.plot.set_data(res, rows, self.tol_xy.value())
        if self.project is not None:
            self.project.meta["vypocet"] = {"zapisnik": zap, "dane": "; ".join(dane), "seznam": seznam,
                                            "koeficient": k, "tol_xy": self.tol_xy.value(),
                                            "tol_z": self.tol_z.value()}
            self.project.save()
        self._fill(rows)
        self.log.setPlainText("\n".join(res.zpravy))
        n = sum(1 for r in rows if r.vypocet is not None and r.student is not None)
        if not res.body:
            self.summary.setText("<span style='color:#B91C1C'><b>Nic se nespočítalo</b> – viz zprávy dole.</span>")
        elif bad:
            self.summary.setText(f"<span style='color:#B91C1C'><b>{len(bad)} rozdílů</b></span> z {n} porovnaných "
                                 "bodů. Záložka <b>Diagnóza</b> ukáže pravděpodobnou příčinu.")
            if diag:
                self.tabs.setCurrentWidget(self.diag)
        else:
            self.summary.setText(f"<span style='color:#15803D'><b>✓ Výpočet souhlasí</b></span> – {n} bodů, "
                                 "všechny rozdíly v povolené toleranci.")
        self.b_save.setEnabled(True)
        self.b_coords.setEnabled(bool(res.body))
        self.b_prot.setEnabled(bool(res.body))
        self.b_list.setEnabled(bool(res.body))
        if not student and res.body:
            self.summary.setText(f"<span style='color:#15803D'><b>Spočítáno {len(res.body)} bodů.</b></span> "
                                 "Výpočetní protokol a seznam uložíte tlačítky vlevo.")

    def _fill_checks(self, res, diag):
        red, green = QColor(185, 28, 28), QColor(21, 128, 61)
        self.kt.setRowCount(0)
        for k in res.kontroly:
            i = self.kt.rowCount()
            self.kt.insertRow(i)
            for c, v in enumerate([("✓ " if k.ok else "✗ ") + k.druh, k.stanovisko, k.bod, k.hodnota,
                                   k.vysvetleni]):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setForeground(QBrush(green if k.ok else red))
                self.kt.setItem(i, c, it)
        nbad = sum(1 for k in res.kontroly if not k.ok)
        self.tabs.setTabText(2, f"Kontrola měření ({nbad} ✗)" if nbad else "Kontrola měření ✓")
        if diag:
            html = "<h3>Pravděpodobné příčiny rozdílů</h3><ul>" + "".join(f"<li style='margin-bottom:6px'>{d}</li>"
                                                                           for d in diag) + "</ul>"
        else:
            html = ("<p style='color:#15803D'><b>Žádná společná příčina rozdílů.</b></p>" if not res.body else
                    "<p>Rozdíly nemají typický vzor (nebo žádné nejsou).</p>")
        html += ("<hr><p style='color:#6B7280'>Diagnóza porovnává vaše body s výpočtem po stanoviscích: pootočení "
                 "kolem stanoviska = jiný orientační posun, rozdíl úměrný délce = měřítkový koeficient, stejný "
                 "posun všech bodů = souřadnice stanoviska, stejný rozdíl výšek = výška stanoviska / přístroje, "
                 "souřadnice jiného bodu = prohozená čísla.</p>")
        self.diag.setHtml(html)

    def _fill(self, rows):
        self.table.setRowCount(0)
        def num(b):
            import re as _re
            d = _re.sub(r"\D", "", b)
            return (0, int(d[-6:])) if d else (1, 0)
        rows = sorted(rows, key=lambda r: (r.poznamka == "v pořádku", num(r.bod), r.bod))
        f = lambda v: "–" if v is None else f"{v:+.3f}"  # noqa: E731
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            calc = ""
            if r.vypocet is not None:
                z = "" if r.vypocet.z is None else f" {r.vypocet.z:.3f}"
                calc = f"{r.vypocet.y:.3f} {r.vypocet.x:.3f}{z}"
            vals = [r.bod, r.stanovisko, f(r.dy), f(r.dx), f(r.dz), r.poznamka, calc]
            ok = r.poznamka == "v pořádku"
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (2, 3, 4):
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if not ok:
                    it.setForeground(QBrush(QColor(185, 28, 28)))
                    if c == 5:
                        f_ = it.font()
                        f_.setBold(True)
                        it.setFont(f_)
                self.table.setItem(i, c, it)

    def save_report(self):
        p, _ = QFileDialog.getSaveFileName(self, "Uložit protokol", "kontrola_vypoctu.txt", "Text (*.txt)")
        if p:
            Path(p).write_text(self.report, encoding="utf-8-sig")

    def protokol_text(self) -> str:
        from ..geodezie.protokol import protokol_polarni
        nazev = self.project.name if self.project is not None else ""
        autor = (self.project.meta.get("autor", "") if self.project is not None else "")
        return protokol_polarni(self.result, self._stations, self._known, nazev=nazev, autor=autor,
                                soubor_souradnic=Path(self._files[1].split(";")[0]).name if self._files[1] else "",
                                soubor_mereni=Path(self._files[0]).name)

    def save_protokol(self, path: str | None = None):
        if self.result is None:
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Výpočetní protokol", "vypocetni_protokol.pdf",
                                                  "PDF (*.pdf);;Text (*.txt)")
        if not path:
            return None
        text = self.protokol_text()
        try:
            if path.lower().endswith(".pdf"):
                from ..geodezie.protokol import protokol_pdf
                protokol_pdf(text, path, self.project.name if self.project is not None else "")
            else:
                Path(path).write_text(text, encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.warning(self, "Výpočetní protokol", f"Protokol nejde uložit: {e}")
            return None
        return path

    def to_list(self):
        win = self.parent()
        page = getattr(win, "vypocty", None)
        if self.result is None or page is None:
            return 0
        from ..geodezie.body import Bod
        nove = [Bod(b.bod, b.y, b.x, b.z, poznamka=f"polární metoda ze st. {b.stanovisko}")
                for b in self.result.body if not b.kontrolni]
        n, konf = page.seznam.pridej(nove, "Polární metoda: vypočtené body")
        page.model.refresh()
        page._after_change()
        QMessageBox.information(self, "Do seznamu bodů", f"Přidáno {n} bodů do seznamu na stránce Výpočty."
                                + (f"\n{len(konf)} čísel už v seznamu bylo a ponechala se původní." if konf else ""))
        return n

    def save_coords(self):
        if self.result is None:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Uložit vypočtené souřadnice", "vypoctene_body.txt", "Text (*.txt)")
        if not p:
            return
        lines = [f"{b.bod:<18}{b.y:>13.3f}{b.x:>14.3f}{'' if b.z is None else f'{b.z:>10.3f}'}"
                 for b in self.result.body if not b.kontrolni]
        Path(p).write_text("\n".join(lines) + "\n", encoding="utf-8")


class DeviationPlot(QWidget):
    """Mapa odchylek: body a stanoviska v poloze, šipky = rozdíl vašeho bodu od výpočtu (zvětšeno)."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(260)
        self.res, self.rows, self.tol = None, [], 0.01

    def set_data(self, res, rows, tol):
        self.res, self.rows, self.tol = res, [r for r in rows if r.vypocet is not None], tol
        self.update()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        if not self.res or not self.rows:
            p.setPen(QColor("#6B7280"))
            p.drawText(self.rect(), Qt.AlignCenter, "Nejdřív spusťte výpočet.")
            return
        pts = [(r.vypocet.y, r.vypocet.x) for r in self.rows] + \
              [(s.y, s.x) for s in self.res.stanoviska.values()]
        ys, xs = [a for a, _ in pts], [b for _, b in pts]
        y0, y1, x0, x1 = min(ys), max(ys), min(xs), max(xs)
        span = max(y1 - y0, x1 - x0, 1.0)
        m = 40
        sc = min((self.width() - 2 * m) / span, (self.height() - 2 * m) / span)

        def to(y, x):  # S-JTSK: Y roste na západ (vlevo), X na jih (dolů)
            return QPointF(self.width() - m - (y - y0) * sc - (self.width() - 2 * m - (y1 - y0) * sc) / 2,
                           m + (x - x0) * sc + (self.height() - 2 * m - (x1 - x0) * sc) / 2)
        dmax = max((r.dxy or 0) for r in self.rows) or self.tol
        k = (0.08 * span) / max(dmax, self.tol)  # největší odchylka = 8 % obrázku
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        for r in self.rows:
            c = to(r.vypocet.y, r.vypocet.x)
            ok = r.poznamka == "v pořádku"
            col = QColor("#16A34A") if ok else QColor("#DC2626")
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(c, 3, 3)
            if r.dy is not None and (r.dxy or 0) > 1e-4:
                t = to(r.vypocet.y + r.dy * k, r.vypocet.x + r.dx * k)
                p.setPen(QPen(col, 1.4))
                p.drawLine(c, t)
            if not ok:
                p.setPen(QColor("#374151"))
                p.drawText(c + QPointF(5, -4), r.bod[-6:])
        for s in self.res.stanoviska.values():
            c = to(s.y, s.x)
            p.setPen(QPen(QColor("#1D4ED8"), 2))
            p.setBrush(QColor("#DBEAFE"))
            p.drawPolygon(QPolygonF([c + QPointF(0, -8), c + QPointF(7, 5), c + QPointF(-7, 5)]))
            p.drawText(c + QPointF(9, 4), s.bod)
        p.setPen(QColor("#6B7280"))
        p.drawText(QRectF(8, self.height() - 22, self.width() - 16, 18), Qt.AlignLeft,
                   f"▲ stanovisko   ● bod (zelený = v toleranci, červený = rozdíl)   šipky = rozdíl vašeho bodu "
                   f"zvětšený {k:.0f}×")
