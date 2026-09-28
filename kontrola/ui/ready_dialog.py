"""„Připraveno k odevzdání?“ – semafor, co zbývá, počítadlo odevzdání a průběh počtu chyb v čase."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton, QVBoxLayout,
                               QWidget)

from ..checks.base import Issue, Severity

MAX_ODEVZDANI = 5


def record_history(project, issues: list[Issue], label: str = "") -> None:
    """Zapíše počty chyb po kontrole do historie projektu (posledních 60 kontrol)."""
    if project is None:
        return
    open_ = [i for i in issues if i.state == "nová"]
    c = Counter(i.severity for i in open_)
    hist = project.meta.setdefault("historie", [])
    hist.append({"cas": dt.datetime.now().isoformat(timespec="seconds"), "chyby": c.get(Severity.CHYBA, 0),
                 "varovani": c.get(Severity.VAROVANI, 0), "info": c.get(Severity.INFO, 0),
                 "vyreseno": len(issues) - len(open_), "pozn": label})
    del hist[:-60]


class HistoryChart(QWidget):
    """Sloupcový graf: počet chyb (červeně) a varování (oranžově) při jednotlivých kontrolách."""

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self.data: list[dict] = []
        self.compact = compact
        self.setMinimumHeight(46 if compact else 160)
        self.setMouseTracking(True)

    def set_data(self, data: list[dict]):
        self.data = list(data or [])[-30:]
        self.setToolTip(self._tip())
        self.update()

    def _tip(self) -> str:
        if not self.data:
            return "Průběh počtu chyb – zatím žádná kontrola."
        first, last = self.data[0], self.data[-1]
        return (f"Průběh počtu chyb v posledních {len(self.data)} kontrolách: chyby {first['chyby']} → "
                f"{last['chyby']}, varování {first['varovani']} → {last['varovani']}.")

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4 if self.compact else -18)
        if not self.data:
            p.setPen(QColor(150, 150, 155))
            p.drawText(self.rect(), Qt.AlignCenter, "Průběh chyb se zobrazí po několika kontrolách.")
            return
        top = max(1, max(d["chyby"] + d["varovani"] for d in self.data))
        n = len(self.data)
        w = min(r.width() / max(n, 8), 16.0 if self.compact else 34.0)
        for k, d in enumerate(self.data):
            x = r.left() + k * w + w * 0.15
            bw = w * 0.7
            hc = r.height() * d["chyby"] / top
            hv = r.height() * d["varovani"] / top
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(220, 38, 38))
            p.drawRoundedRect(QRectF(x, r.bottom() - hc, bw, hc), 2, 2)
            p.setBrush(QColor(245, 158, 11))
            p.drawRoundedRect(QRectF(x, r.bottom() - hc - hv, bw, hv), 2, 2)
            if not self.compact and (k == n - 1 or k == 0):
                p.setPen(QColor(90, 90, 100))
                f = QFont(self.font())
                f.setPointSizeF(max(7.0, f.pointSizeF() - 1.5))
                p.setFont(f)
                p.drawText(QRectF(x - 20, r.bottom() + 2, bw + 40, 14), Qt.AlignHCenter,
                           f"{d['chyby']}/{d['varovani']}")
        p.setPen(QPen(QColor(209, 213, 219), 1))
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))


class ReadyDialog(QDialog):
    def __init__(self, project, issues: list[Issue], checklist: list[tuple[bool | None, str]], parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Připraveno k odevzdání?")
        self.resize(720, 640)
        lay = QVBoxLayout(self)
        open_ = [i for i in issues if i.state == "nová"]
        errs = [i for i in open_ if i.severity == Severity.CHYBA]
        warns = [i for i in open_ if i.severity == Severity.VAROVANI]
        ignored = [i for i in issues if i.state == "ignorovat"]
        if errs:
            color, title, text = "#DC2626", f"Ještě ne – {len(errs)} chyb", \
                "Tyto chyby by učitelova kontrola nejspíš našla. Opravte je v MicroStationu a uložte DXF znovu."
        elif warns:
            color, title, text = "#F59E0B", f"Skoro – 0 chyb, {len(warns)} varování", \
                "Chyby nejsou. Projděte varování (volné konce, body blízko sebe…) – když jsou v pořádku, " \
                "označte je Ignorovat."
        else:
            color, title, text = "#16A34A", "Ano – výkres je připravený", \
                "Kontrola nenašla žádné chyby ani varování. Můžete odevzdat."
        head = QHBoxLayout()
        light = QLabel()
        light.setFixedSize(56, 56)
        light.setStyleSheet(f"background: {color}; border-radius: 28px; border: 4px solid #E5E7EB;")
        head.addWidget(light)
        t = QLabel(f"<p style='font-size:18px; font-weight:700; color:{color}; margin:0'>{title}</p>"
                   f"<p style='margin-top:4px'>{text}</p>")
        t.setWordWrap(True)
        head.addWidget(t, 1)
        lay.addLayout(head)
        if errs or warns:
            lst = QListWidget()
            for name, n in Counter(i.check_name for i in errs).most_common():
                lst.addItem(f"● chyba – {name}: {n}×")
            for name, n in Counter(i.check_name for i in warns).most_common():
                lst.addItem(f"○ varování – {name}: {n}×")
            lst.setMaximumHeight(min(130, 24 * lst.count() + 8))
            lay.addWidget(lst)
        if ignored:
            lay.addWidget(QLabel(f"Ignorovaných chyb: {len(ignored)} – ujistěte se, že jsou opravdu v pořádku."))
        lay.addWidget(QLabel("<b>Kontrolní seznam</b>"))
        for ok, txt in checklist:
            mark = {True: "<span style='color:#16A34A'>✓</span>", False: "<span style='color:#DC2626'>✗</span>",
                    None: "<span style='color:#9CA3AF'>–</span>"}[ok]
            lab = QLabel(f"{mark} {txt}")
            lab.setWordWrap(True)
            lay.addWidget(lab)
        lay.addWidget(QLabel("<b>Průběh počtu chyb</b> (červeně chyby, oranžově varování)"))
        self.chart = HistoryChart()
        self.chart.set_data(project.meta.get("historie", []) if project else [])
        lay.addWidget(self.chart, 1)

        self.odev_label = QLabel()
        self.odev_label.setWordWrap(True)
        lay.addWidget(self.odev_label)
        row = QHBoxLayout()
        self.b_rec = QPushButton("Zaznamenat odevzdání")
        self.b_rec.setToolTip("Až výkres odevzdáte, zaznamenejte to – aplikace hlídá počet pokusů "
                              f"(nejvýše {MAX_ODEVZDANI}).")
        self.b_rec.clicked.connect(lambda: self._record(len(errs), len(warns)))
        self.b_undo = QPushButton("Zrušit poslední záznam")
        self.b_undo.clicked.connect(self._undo)
        close = QPushButton("Zavřít")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(self.b_rec)
        row.addWidget(self.b_undo)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self._refresh_odev()

    def _odev(self) -> list[dict]:
        return self.project.meta.setdefault("odevzdani", []) if self.project else []

    def _refresh_odev(self):
        od = self._odev()
        left = MAX_ODEVZDANI - len(od)
        hist = "".join(f"<br>{k}. {d['datum']} – chyb při odevzdání: {d['chyby']}" for k, d in enumerate(od, 1))
        warn = ""
        if left <= 1:
            warn = (" <span style='color:#DC2626'><b>Pozor – zbývá poslední pokus!</b></span>" if left == 1 else
                    " <span style='color:#DC2626'><b>Všechny pokusy vyčerpány.</b></span>")
        self.odev_label.setText(f"<b>Odevzdání:</b> {len(od)} z {MAX_ODEVZDANI} (zbývá {max(0, left)}).{warn}{hist}")
        self.b_undo.setEnabled(bool(od))

    def _record(self, errs: int, warns: int):
        od = self._odev()
        if len(od) >= MAX_ODEVZDANI:
            QMessageBox.warning(self, "Odevzdání", f"Už je zaznamenáno {MAX_ODEVZDANI} odevzdání.")
            return
        if errs and QMessageBox.question(self, "Odevzdání", f"Výkres má ještě {errs} chyb. Opravdu ho odevzdáváte?"
                                         ) != QMessageBox.Yes:
            return
        od.append({"datum": dt.datetime.now().strftime("%d.%m.%Y %H:%M"), "chyby": errs, "varovani": warns})
        self.project.save()
        self._refresh_odev()

    def _undo(self):
        od = self._odev()
        if od:
            od.pop()
            self.project.save()
            self._refresh_odev()


def checklist_for(project, drawing, config) -> list[tuple[bool | None, str]]:
    """Body kontrolního seznamu před odevzdáním."""
    out: list[tuple[bool | None, str]] = []
    out.append((bool(project.rules.pravidla), f"Pravidla z tabulky atributů načtena ({len(project.rules.pravidla)})"
                if project.rules.pravidla else "Nejsou načtena pravidla – atributy (vrstvy, barvy, styly) se "
                "nekontrolovaly. Zadání → Tabulka atributů / Pravidla."))
    out.append((not config.rozpracovany, "Režim „Rozpracovaný výkres“ je vypnutý" if not config.rozpracovany else
                "Zapnutý „Rozpracovaný výkres“ – pro tuto kontrolu se ignoruje, ale nezapomeňte ho vypnout."))
    has_list = bool(project.attachments("seznamy"))
    out.append((True if has_list else None, "Výkres porovnán se seznamem souřadnic" if has_list else
                "Seznam souřadnic není nahraný (Podklady → Přidat → Seznam souřadnic) – body se neporovnaly."))
    src = Path(drawing.source_path or drawing.path) if drawing else None
    if src is not None:
        dgn = src.with_suffix(".dgn")
        if dgn.is_file() and src.suffix.lower() == ".dxf":
            fresh = src.stat().st_mtime >= dgn.stat().st_mtime - 2
            out.append((fresh, "DXF je uložené po poslední změně DGN" if fresh else
                        "DGN je novější než DXF – v MicroStationu znovu uložte DXF, jinak kontrolujete starý stav."))
    docs = [a for a in project.attachments("dokumenty")
            if Path(a.name).suffix.lower() in (".doc", ".docx", ".odt", ".rtf", ".pdf")]
    if docs:
        from ..importer.dokument import layer_rules, read_document, requirements
        n_req, missing = 0, []
        for a in docs:
            try:
                d = read_document(a.path)
            except Exception:  # noqa: BLE001
                continue
            n_req += sum(1 for q in requirements(d) if q.druh == "Pokyn")
            have = {r.hladina for r in project.rules.pravidla}
            missing += [r.hladina for r in layer_rules(d) if r.hladina not in have]
        if missing:
            out.append((False, f"Vrstvy {', '.join(missing)} ze zadání (Word) nejsou v pravidlech – Zadání → Pokyny "
                               "ze zadání → Přidat vrstvy do pravidel."))
        if n_req:
            out.append((None, f"Projděte {n_req} pokynů ze zadání (Zadání → Pokyny ze zadání) – např. název "
                              "souboru, komprimace výkresu, tabulka barev."))
    vp = project.meta.get("vypocet") or {}
    if vp.get("zapisnik"):
        out.append((None, "Výpočet souřadnic ze zápisníku jste si ověřili v okně Kontrola výpočtu souřadnic."))
    return out
