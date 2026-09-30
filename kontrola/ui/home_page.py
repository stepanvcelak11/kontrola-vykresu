"""Úvodní obrazovka: kde v práci jsem (zadání → výkres → kontrola → odevzdání) a rychlé nástroje."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QTableWidgetItem, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)


class ScoreGauge(QWidget):
    """Kruhový ukazatel skóre 0–100."""

    def __init__(self, size: int = 110, parent=None):
        super().__init__(parent)
        self._size = size
        self.value: int | None = None
        self.color = QColor("#9CA3AF")
        self.caption = ""
        self.setFixedSize(size, size)

    def set_score(self, value: int | None, color: str = "#9CA3AF", caption: str = ""):
        self.value, self.color, self.caption = value, QColor(color), caption
        self.setToolTip(caption)
        self.update()

    def sizeHint(self):  # noqa: N802
        return QSize(self._size, self._size)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self._size
        pen_w = max(4.0, w * 0.09)
        r = QRectF(pen_w / 2 + 1, pen_w / 2 + 1, w - pen_w - 2, w - pen_w - 2)
        track = QColor(self.palette().mid().color())
        track.setAlpha(60)
        p.setPen(QPen(track, pen_w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 225 * 16, -270 * 16)
        if self.value is not None:
            p.setPen(QPen(self.color, pen_w, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(r, 225 * 16, int(-270 * 16 * max(0, min(100, self.value)) / 100))
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(max(8.0, w * 0.2))
        p.setFont(f)
        p.setPen(self.palette().text().color())
        p.drawText(QRectF(0, 0, w, w * 0.92), Qt.AlignCenter, "–" if self.value is None else str(self.value))
        if w >= 80:
            f.setBold(False)
            f.setPointSizeF(max(6.5, w * 0.075))
            p.setFont(f)
            p.setPen(self.palette().mid().color())
            p.drawText(QRectF(0, w * 0.62, w, w * 0.2), Qt.AlignCenter, "ze 100")


class StepCard(QFrame):
    def __init__(self, number: int, title: str, button: str, parent=None):
        super().__init__(parent)
        self.setObjectName("karta")
        self.setMinimumWidth(210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        head = QHBoxLayout()
        self.number = number
        self.badge = QLabel(str(number))
        self.badge.setFixedSize(30, 30)
        self.badge.setAlignment(Qt.AlignCenter)
        head.addWidget(self.badge)
        t = QLabel(title)
        t.setObjectName("krok_nadpis")
        head.addWidget(t, 1)
        lay.addLayout(head)
        self.body = QHBoxLayout()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status.setMinimumHeight(54)
        self.status.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.body.addWidget(self.status, 1)
        lay.addLayout(self.body, 1)
        self.button = QPushButton(button)
        lay.addWidget(self.button)
        self.set_state(None)

    def set_state(self, done: bool | None):
        col = {True: "#16A34A", False: "#2563EB", None: "#9CA3AF"}[done]
        self.badge.setText("✓" if done else str(self.number))
        self.badge.setStyleSheet(f"background:{col}; color:white; border-radius:15px; font-weight:700;")


class HomePage(QScrollArea):
    """Signály volá hlavní okno – stránka sama nic nedělá, jen ukazuje stav a nabízí kroky."""
    openRecent = Signal(str)

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        self.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(18)
        head = QHBoxLayout()
        logo = QLabel()
        try:
            from ..resources import resource_path
            pm = QPixmap(str(resource_path("ikona.png")))
            if not pm.isNull():
                logo.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:  # noqa: BLE001
            pass
        head.addWidget(logo)
        tbox = QVBoxLayout()
        self.title = QLabel("Kontrola výkresu")
        self.title.setObjectName("uvod_nadpis")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("uvod_podnadpis")
        tbox.addWidget(self.title)
        tbox.addWidget(self.subtitle)
        head.addLayout(tbox, 1)
        lay.addLayout(head)

        steps = QHBoxLayout()
        steps.setSpacing(14)
        self.c_zad = StepCard(1, "Zadání a pravidla", "Otevřít Zadání")
        self.c_vyk = StepCard(2, "Výkres", "Otevřít výkres…")
        self.c_kon = StepCard(3, "Kontrola", "Zkontrolovat (F5)")
        self.c_ode = StepCard(4, "Odevzdání", "Připraveno k odevzdání?")
        self.gauge = ScoreGauge(96)
        self.c_kon.body.addWidget(self.gauge)
        self.c_kon.button.setProperty("primarni", True)
        for c in (self.c_zad, self.c_vyk, self.c_kon, self.c_ode):
            steps.addWidget(c, 1)
        lay.addLayout(steps)
        self.c_zad.button.clicked.connect(lambda: win.tabs.setCurrentWidget(win.zadani))
        self.c_vyk.button.clicked.connect(win.open_dialog)
        self.c_kon.button.clicked.connect(lambda: (win.tabs.setCurrentWidget(win.split), win.a_check.trigger()))
        self.c_ode.button.clicked.connect(win.ready_check)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        rec = QFrame()
        rec.setObjectName("karta")
        rl = QVBoxLayout(rec)
        rl.setContentsMargins(16, 14, 16, 14)
        lab = QLabel("Moje práce")
        lab.setObjectName("krok_nadpis")
        rl.addWidget(lab)
        from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTabWidget
        self.work_tabs = QTabWidget()
        self.projects = QTableWidget(0, 5)
        self.projects.setHorizontalHeaderLabels(["Projekt", "Výkres", "Naposledy", "Poslední kontrola", "Odevzdáno"])
        self.projects.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.projects.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.projects.verticalHeader().setVisible(False)
        self.projects.setShowGrid(False)
        self.projects.setAlternatingRowColors(True)
        hh = self.projects.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c, w_ in ((2, 110), (3, 150), (4, 105)):
            self.projects.setColumnWidth(c, w_)
        self.projects.cellDoubleClicked.connect(self._open_project_row)
        self.projects.setMinimumHeight(170)
        self.work_tabs.addTab(self.projects, "Rozpracované projekty")
        self.recent = QListWidget()
        self.recent.itemActivated.connect(lambda it: self.openRecent.emit(it.data(Qt.UserRole)))
        self.recent.itemDoubleClicked.connect(lambda it: self.openRecent.emit(it.data(Qt.UserRole)))
        self.work_tabs.addTab(self.recent, "Naposledy otevřené výkresy")
        rl.addWidget(self.work_tabs, 1)
        hint = QLabel("Dvojklik otevře projekt i s výkresem a výsledky poslední kontroly.")
        hint.setObjectName("karta_popis")
        hint.setWordWrap(True)
        rl.addWidget(hint)
        bottom.addWidget(rec, 3)

        tools = QFrame()
        tools.setObjectName("karta")
        tl = QVBoxLayout(tools)
        tl.setContentsMargins(16, 14, 16, 14)
        lab = QLabel("Nástroje")
        lab.setObjectName("krok_nadpis")
        tl.addWidget(lab)
        grid = QGridLayout()
        grid.setSpacing(8)
        items = [("Ověřit seznam souřadnic", win.verify_list), ("Body ze seznamu do DXF", win.points_to_dxf), ("Kontrola výpočtu (Groma)", win.show_vypocet), ("Porovnat verze výkresu", win.compare_versions),
                 ("Rychlé tipy MicroStation", win.show_tips), ("Co znamenají chyby", win.show_help),
                 ("Seznam k opravě (PDF)", lambda: win.export("todo")), ("Protokol od učitele", win.compare_teacher),
                 ("Hromadná kontrola", win.batch_check), ("Protokol HTML", lambda: win.export("html")),
                 ("Průvodce", win.show_guide), ("Nastavení kontrol", win.edit_settings)]
        for k, (text, slot) in enumerate(items):
            b = QPushButton(text)
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _c=False, s=slot: s())
            grid.addWidget(b, k // 2, k % 2)
        tl.addLayout(grid)
        tl.addStretch(1)
        bottom.addWidget(tools, 2)
        lay.addLayout(bottom, 1)
        self.score_detail = QLabel()
        self.score_detail.setObjectName("karta_popis")
        self.score_detail.setWordWrap(True)
        lay.addWidget(self.score_detail)
        lay.addStretch(1)

    def _open_project_row(self, row, _col=0):
        it = self.projects.item(row, 0)
        if it is not None and it.data(Qt.UserRole):
            root = it.data(Qt.UserRole)
            cur = getattr(self.win, "project", None)
            if cur is None or str(cur.root) != root:
                self.win.open_project(root)

    def _fill_projects(self):
        import datetime as dt

        import yaml

        from ..project import default_projects_dir
        roots: set[Path] = set()
        cur = getattr(self.win, "project", None)
        dirs = {default_projects_dir()}
        if cur is not None:
            dirs.add(Path(cur.root).parent)
        for d in dirs:
            if d.is_dir():
                for sub in d.iterdir():
                    if (sub / "projekt.yaml").is_file():
                        roots.add(sub.resolve())
        rows = []
        for r in roots:
            if cur is not None and Path(cur.root).resolve() == r:
                meta = cur.meta  # otevřený projekt – aktuální stav z paměti
            else:
                try:
                    meta = yaml.safe_load((r / "projekt.yaml").read_text(encoding="utf-8")) or {}
                except Exception:  # noqa: BLE001
                    continue
            hist = meta.get("historie") or []
            last = hist[-1] if hist else None
            rows.append((meta.get("ulozeno", ""), r, meta, last))
        rows.sort(key=lambda t: str(t[0]), reverse=True)
        self.projects.setRowCount(len(rows))
        for i, (saved, r, meta, last) in enumerate(rows):
            try:
                when = dt.datetime.fromisoformat(str(saved)).strftime("%d.%m. %H:%M") if saved else "–"
            except ValueError:
                when = str(saved)
            src = meta.get("vykres_zdroj") or meta.get("vykres") or ""
            kon = (f"{last.get('chyby', 0)} chyb, {last.get('varovani', 0)} var." if last else "–")
            vals = [meta.get("nazev") or r.name, Path(src).name if src else "–", when, kon,
                    f"{len(meta.get('odevzdani') or [])}×"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setData(Qt.UserRole, str(r))
                    it.setToolTip(str(r))
                    if cur is not None and Path(cur.root).resolve() == r:
                        f = it.font()
                        f.setBold(True)
                        it.setFont(f)
                        it.setText("● " + v)
                        it.setToolTip(f"Otevřený projekt – {r}")
                if c == 3 and last and last.get("chyby", 0) == 0:
                    it.setForeground(QColor("#16A34A"))
                self.projects.setItem(i, c, it)

    def refresh(self):
        win = self.win
        p = getattr(win, "project", None)
        from .. import __version__
        self.subtitle.setText(f"Projekt: <b>{p.name if p else '–'}</b> · verze {__version__}")
        n_rules = len(p.rules.pravidla) if p else 0
        docs = len(p.attachments("dokumenty")) if p else 0
        lists = len(p.attachments("seznamy")) if p else 0
        self.c_zad.status.setText(
            (f"<span style='color:#16A34A'>✓ {n_rules} pravidel</span>" if n_rules else
             "<span style='color:#B45309'>Zatím žádná pravidla</span> – nahrajte Směrnici (Excel/PDF) a Word se "
             "zadáním.") + (f"<br>Dokumenty: {docs}" if docs else "") + (f"<br>Seznam souřadnic: ✓" if lists else ""))
        self.c_zad.set_state(True if n_rules else False)
        d = getattr(win, "drawing", None)
        if d is not None:
            name = Path(d.source_path or d.path).name
            self.c_vyk.status.setText(f"<span style='color:#16A34A'>✓ {name}</span><br>{len(d.features)} prvků, "
                                      f"{sum(1 for li in d.layers.values() if li.count)} vrstev")
        else:
            self.c_vyk.status.setText("Zatím není otevřený žádný výkres.<br>Uložte v MicroStationu DXF a otevřete "
                                      "ho.")
        self.c_vyk.set_state(True if d is not None else (False if n_rules else None))
        issues = getattr(win, "issues", []) or []
        checked = bool(getattr(win, "_checked_once", False)) and d is not None
        if checked:
            from ..skore import compute_score
            sk = compute_score(issues, bool(n_rules))
            self.gauge.set_score(sk.hodnota, sk.barva, sk.popis)
            todo = sum(1 for i in issues if i.state == "nová" and i.severity.value != "info")
            self.c_kon.status.setText(f"<b style='color:{sk.barva}'>{sk.popis}</b><br>k opravě: {todo}")
            self.c_kon.set_state(sk.hodnota >= 100)
            self.score_detail.setText("Skóre připravenosti (orientační, ne známka): " + (
                ", ".join(f"{co} −{s}" for co, s in sk.rozpad) if sk.rozpad else "bez srážek") + ".")
        else:
            self.gauge.set_score(None)
            self.c_kon.status.setText("Výkres zatím nebyl zkontrolován.")
            self.c_kon.set_state(False if d is not None else None)
            self.score_detail.setText("")
        from .ready_dialog import MAX_ODEVZDANI
        od = len(p.meta.get("odevzdani", [])) if p else 0
        self.c_ode.status.setText(f"Odevzdáno {od} z {MAX_ODEVZDANI}.<br>Před odevzdáním spusťte úplnou "
                                  "kontrolu s tolerancemi učitele.")
        self.c_ode.set_state(True if od else None)
        self._fill_projects()
        self.recent.clear()
        items = win.settings.value("cesty/posledni_vykresy", []) or []
        if isinstance(items, str):
            items = [items]
        for path in items:
            if Path(path).is_file():
                it = QListWidgetItem(f"{Path(path).name}    —    {Path(path).parent}")
                it.setData(Qt.UserRole, path)
                it.setToolTip(path)
                self.recent.addItem(it)
        if not self.recent.count():
            it = QListWidgetItem("(zatím nic)")
            it.setFlags(Qt.NoItemFlags)
            self.recent.addItem(it)
