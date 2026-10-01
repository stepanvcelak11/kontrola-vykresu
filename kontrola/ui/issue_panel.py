"""Panel se seznamem chyb, filtry a tlačítky pro procházení."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import (QAbstractTableModel, QItemSelectionModel, QModelIndex, QSortFilterProxyModel,
                            Qt, Signal)
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QPushButton, QSplitter, QStyle, QStyledItemDelegate, QTableView, QVBoxLayout,
                               QWidget)

from ..checks.base import ISSUE_STATES, Issue, Severity, fmt_num
from .drawing_view import SEVERITY_COLORS

COLUMNS = ["Č.", "Závažnost", "Stav", "Popis", "Typ kontroly", "Vrstva", "X", "Y"]
C_SEV, C_STATE, C_DESC, C_TYPE = 1, 2, 3, 4
STATE_LABEL = {"nová": "k opravě", "opraveno": "✓ opraveno", "ignorovat": "✕ ignorováno"}
STATE_COLOR = {"opraveno": QColor(22, 150, 70), "ignorovat": QColor(120, 120, 130)}


def fmt_coord(v: float) -> str:
    return f"{v:,.3f}".replace(",", " ").replace(".", ",")


_DOTS: dict = {}


def _dot(color: QColor, faded: bool) -> QPixmap:
    key = (color.name(), faded)
    if key not in _DOTS:
        pm = QPixmap(10, 10)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(color)
        if faded:
            c.setAlpha(90)
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawEllipse(1, 1, 8, 8)
        p.end()
        _DOTS[key] = pm
    return _DOTS[key]


class BadgeDelegate(QStyledItemDelegate):
    """Závažnost a stav jako barevný štítek (pilulka) – na první pohled čitelné."""

    def paint(self, painter, option, index):
        opt = option
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        opt.icon = type(opt.icon)()
        style = opt.widget.style() if opt.widget else None
        if style is not None:
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        brush = index.data(Qt.ForegroundRole)
        col = brush.color() if isinstance(brush, QBrush) else QColor(107, 114, 128)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        f = QFont(opt.font)
        f.setBold(True)
        f.setPointSizeF(max(7.5, f.pointSizeF() - 0.8))
        painter.setFont(f)
        fm = painter.fontMetrics()
        w = min(opt.rect.width() - 8, fm.horizontalAdvance(text) + 18)
        h = fm.height() + 4
        r = opt.rect.adjusted(4, 0, 0, 0)
        r.setWidth(w)
        r.setTop(opt.rect.center().y() - h // 2)
        r.setHeight(h)
        bg = QColor(col)
        bg.setAlpha(34)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(r, h / 2, h / 2)
        painter.setPen(col)
        painter.drawText(r, Qt.AlignCenter, text)
        painter.restore()


_GROUP_ICON = {"Topologie": "sk_topologie", "Atributy": "sk_atributy", "Kartografie": "sk_kartografie",
               "Geometrie": "sk_geometrie"}


class CardDelegate(QStyledItemDelegate):
    """Řádek seznamu chyb jako karta: ikona skupiny, popis, typ a vrstva, stav – jako v mapových aplikacích."""

    HEIGHT = 64

    def __init__(self, panel):
        super().__init__(panel.table)
        self.panel = panel
        self._icons: dict[tuple, object] = {}

    @classmethod
    def height(cls) -> int:
        """Výška karty podle písma (větší písmo v Zobrazení → Velikost písma = vyšší karty)."""
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtWidgets import QApplication
        fm = QFontMetrics(QApplication.font())
        return max(cls.HEIGHT, int(fm.height() * 2 + 30))

    def sizeHint(self, option, index):  # noqa: N802
        from PySide6.QtCore import QSize
        return QSize(option.rect.width(), self.height())

    def _icon(self, name: str, color: str):
        key = (name, color)
        if key not in self._icons:
            from .theme import icon
            self._icons[key] = icon(name, color, 40).pixmap(20, 20)
        return self._icons[key]

    def paint(self, painter, option, index):
        from PySide6.QtCore import QRectF

        from .theme import accent, themed
        src = self.panel.proxy.mapToSource(index)
        iss: Issue = self.panel.model.issues[src.row()]
        r = QRectF(option.rect).adjusted(4, 3, -4, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        sev = QColor(SEVERITY_COLORS.get(iss.severity, QColor(128, 128, 128)))
        done = iss.state != "nová"
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        bg = QColor(accent("#E8F0FE") if selected else themed("#F8FAFC") if hover else themed("#FFFFFF"))
        painter.setPen(QPen(QColor(accent() if selected else themed("#E3E7EE")), 1.4 if selected else 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(r, 10, 10)
        # ikona skupiny v kroužku barvy závažnosti
        c = QRectF(r.left() + 10, r.center().y() - 17, 34, 34)
        ring = QColor(sev if not done else QColor(150, 150, 155))
        fill = QColor(ring)
        fill.setAlpha(36)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(c)
        grp = check_group(iss.check_id)
        pm = self._icon(_GROUP_ICON.get(grp, "sk_topologie"), ring.name())
        painter.drawPixmap(int(c.center().x() - 10), int(c.center().y() - 10), pm)
        # texty
        x0 = c.right() + 10
        right_w = 96
        f = QFont(option.font)
        f.setPointSizeF(f.pointSizeF() + 0.3)
        f.setBold(True)
        f.setStrikeOut(done and iss.state == "opraveno")
        painter.setFont(f)
        fm = painter.fontMetrics()
        top = QRectF(x0, r.top() + 9, r.right() - x0 - right_w - 6, fm.height())
        painter.setPen(QColor(themed("#9CA3AF") if done else themed("#111827")))
        painter.drawText(top, Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(iss.message, Qt.ElideRight,
                                                                            int(top.width())))
        f2 = QFont(option.font)
        f2.setPointSizeF(max(7.5, f2.pointSizeF() - 0.6))
        painter.setFont(f2)
        fm2 = painter.fontMetrics()
        sub = f"#{iss.number} · {iss.check_name}" + (f" · {iss.layer}" if iss.layer else "")
        near = len(self.panel.near.get(iss.number, ()))
        if near:
            sub = f"⧉ +{near} · " + sub
        bot = QRectF(x0, top.bottom() + 4, r.right() - x0 - 10, fm2.height())
        painter.setPen(QColor(themed("#6B7280")))
        painter.drawText(bot, Qt.AlignLeft | Qt.AlignVCenter, fm2.elidedText(sub, Qt.ElideRight, int(bot.width())))
        # štítek vpravo nahoře: stav (nová/opraveno/ignorováno), jinak závažnost
        if iss.state == "opraveno":
            label, col = "✓ opraveno", QColor(22, 163, 74)
        elif iss.state == "ignorovat":
            label, col = "✕ ignorováno", QColor(120, 120, 130)
        elif iss.nove:
            label, col = "★ nová", QColor(124, 58, 237)
        else:
            label, col = iss.severity.value, sev
        fb = QFont(option.font)
        fb.setBold(True)
        fb.setPointSizeF(max(7.5, fb.pointSizeF() - 1))
        painter.setFont(fb)
        fmb = painter.fontMetrics()
        bw, bh = fmb.horizontalAdvance(label) + 16, fmb.height() + 4
        br = QRectF(r.right() - bw - 10, r.top() + 8, bw, bh)
        pill = QColor(col)
        pill.setAlpha(34)
        painter.setPen(Qt.NoPen)
        painter.setBrush(pill)
        painter.drawRoundedRect(br, bh / 2, bh / 2)
        painter.setPen(col)
        painter.drawText(br, Qt.AlignCenter, label)
        painter.restore()


class IssueModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.issues: list[Issue] = []

    def set_issues(self, issues: list[Issue]):
        self.beginResetModel()
        self.issues = list(issues)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.issues)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        iss = self.issues[index.row()]
        c = index.column()
        done = iss.state != "nová"
        if role == Qt.DisplayRole:
            state = "★ nová" if (iss.nove and iss.state == "nová") else STATE_LABEL.get(iss.state, iss.state)
            return [str(iss.number), iss.severity.value, state, iss.message,
                    iss.check_name, iss.layer, fmt_coord(iss.x), fmt_coord(iss.y)][c]
        if role == Qt.UserRole:  # řazení
            return [iss.number, iss.severity.rank, ISSUE_STATES.index(iss.state) if iss.state in ISSUE_STATES else 0,
                    iss.message, iss.check_name, iss.layer, iss.x, iss.y][c]
        if role == Qt.ForegroundRole:
            if c == C_STATE and done:
                return QBrush(STATE_COLOR.get(iss.state, QColor(120, 120, 130)))
            if done:
                return QBrush(QColor(150, 150, 155))
            if c == C_SEV:
                return QBrush(SEVERITY_COLORS.get(iss.severity))
            if c == C_STATE:
                return QBrush(QColor(124, 58, 237) if iss.nove else QColor(107, 114, 128))
        if role == Qt.FontRole and done:
            f = QFont()
            if c == C_STATE:
                f.setBold(True)
            elif c in (C_DESC, C_TYPE):
                f.setStrikeOut(True)
            return f
        if role == Qt.BackgroundRole and iss.state == "opraveno":
            from .theme import is_dark
            return QBrush(QColor(20, 60, 38) if is_dark() else QColor(236, 253, 243))
        if role == Qt.ToolTipRole:
            tip = f"{iss.check_name}: {iss.message}"
            from ..navody import navod
            if navod(iss):
                tip += f"\n\nJak opravit: {navod(iss)}"
            if iss.handles:
                tip += f"\nPrvky (handle): {', '.join(iss.handles[:6])}"
            if iss.note:
                tip += f"\nPoznámka: {iss.note}"
            return tip
        if role == Qt.DecorationRole and c == C_SEV:
            return _dot(SEVERITY_COLORS.get(iss.severity), iss.state != "nová")
        if role == Qt.TextAlignmentRole and c in (0, 6, 7):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def row_of(self, number: int) -> int:
        for i, iss in enumerate(self.issues):
            if iss.number == number:
                return i
        return -1

    def refresh_row(self, row: int):
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))


def check_group(check_id: str) -> str:
    from ..checks.base import REGISTRY
    cls = REGISTRY.get(check_id)
    return getattr(cls, "skupina", "") if cls else ""


QUICK_FILTERS = ((None, "Vše", "Zobrazit všechny nálezy"),
                 ("chyby", "K opravě", "Jen chyby a varování (bez informací)"),
                 ("Topologie", "Topologie", "Jen topologické chyby – napojení, křížení, duplicity (kontrola MGEO)"),
                 ("Atributy", "Atributy", "Jen atributy – vrstva, barva, styl, písmo (kontrola GISoft)"),
                 ("Kartografie", "Kartografie", "Jak mapa vypadá: popisy přes sebe, přes čáry, vzhůru nohama, "
                                                "čísla daleko od bodů"),
                 ("Geometrie", "Geometrie", "Zbytečné lomové body, špičky, nepatrné a úzké plochy"),
                 ("nove", "★ Nové", "Jen chyby, které přibyly od minulé kontroly (co se opravou nově rozbilo)"))


class IssueFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hidden_types: set[str] = set()
        self.severities: set[Severity] = set(Severity)
        self.layer: str | None = None
        self.region: tuple[float, float, float, float] | None = None  # jen chyby v tomto výřezu
        self.hide_done = False
        self.text = ""
        self.group: str | None = None  # rychlý filtr: None | "chyby" | skupina kontroly („Topologie“, …)
        self.setSortRole(Qt.UserRole)

    def filterAcceptsRow(self, row, parent):  # noqa: N802
        iss: Issue = self.sourceModel().issues[row]
        return self.accepts(iss)

    def accepts(self, iss: Issue) -> bool:
        if iss.check_name in self.hidden_types:
            return False
        if iss.severity not in self.severities:
            return False
        if self.group == "chyby":
            if iss.severity == Severity.INFO:
                return False
        elif self.group == "nove":
            if not iss.nove:
                return False
        elif self.group and check_group(iss.check_id) != self.group:
            return False
        if self.layer and iss.layer != self.layer:
            return False
        if self.region is not None:
            x0, y0, x1, y1 = self.region
            if not (x0 <= iss.x <= x1 and y0 <= iss.y <= y1):
                return False
        if self.hide_done and iss.state != "nová":
            return False
        if self.text:
            hay = f"{iss.number} {iss.check_name} {iss.message} {iss.layer} {iss.note} {' '.join(iss.handles)}"
            if self.text not in hay.lower():
                return False
        return True

    def accepts_region(self, iss: Issue) -> bool:
        x0, y0, x1, y1 = self.region
        return x0 <= iss.x <= x1 and y0 <= iss.y <= y1

    def refresh(self):
        self.invalidateFilter()


class IssuePanel(QWidget):
    issueSelected = Signal(int)
    message = Signal(str)  # krátká zpráva do stavového řádku
    filterChanged = Signal(object)  # set[int] viditelných čísel chyb
    stateChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.near: dict[int, list[int]] = {}  # číslo chyby → čísla chyb na stejném místě
        self._undo: list[list[tuple[Issue, str]]] = []  # historie změn stavu pro Zpět (Ctrl+Z)
        self.model = IssueModel(self)
        self.proxy = IssueFilter(self)
        self.proxy.setSourceModel(self.model)
        self._updating = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        cards = QHBoxLayout()
        cards.setSpacing(6)
        self.cards: dict[object, QLabel] = {}
        self.card_caps: dict[object, QLabel] = {}
        for key, title, color in ((None, "k opravě", "palette(text)"),
                                  (Severity.CHYBA, "chyby", SEVERITY_COLORS[Severity.CHYBA].name()),
                                  (Severity.VAROVANI, "varování", SEVERITY_COLORS[Severity.VAROVANI].name()),
                                  (Severity.INFO, "info", SEVERITY_COLORS[Severity.INFO].name())):
            fr = QFrame()
            fr.setObjectName("karta")
            fl_ = QVBoxLayout(fr)
            fl_.setContentsMargins(10, 6, 10, 6)
            fl_.setSpacing(0)
            num = QLabel("–")
            num.setObjectName("karta_cislo")
            num.setStyleSheet(f"color: {color};")
            cap = QLabel(title)
            cap.setObjectName("karta_popis")
            fl_.addWidget(num)
            fl_.addWidget(cap)
            if key is not None:
                fr.setToolTip(f"Kliknutím zobrazíte jen: {title}")
                fr.mousePressEvent = lambda _e, k=key: self._only_severity(k)
                fr.setCursor(Qt.PointingHandCursor)
            else:
                fr.setToolTip("Kliknutím zobrazíte vše")
                fr.mousePressEvent = lambda _e: self.show_all()
                fr.setCursor(Qt.PointingHandCursor)
            self.cards[key] = num
            self.card_caps[key] = cap
            cards.addWidget(fr, 1)
        from .home_page import ScoreGauge
        self.gauge = ScoreGauge(58)
        self.gauge.setVisible(False)
        cards.addWidget(self.gauge)
        lay.addLayout(cards)
        from .ready_dialog import HistoryChart
        self.history = HistoryChart(compact=True)
        self.history.setFixedHeight(40)
        lay.addWidget(self.history)
        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        lay.addWidget(self.banner)
        self.summary = QLabel("Zatím neproběhla žádná kontrola. Otevřete výkres a stiskněte Zkontrolovat (F5).")
        self.summary.setObjectName("souhrn")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        from .flow import FlowLayout
        chips = QWidget()
        qrow = FlowLayout(chips, 4)  # rychlé filtry se zalamují do řádků (úzký plovoucí panel)
        self.quick: dict[object, QPushButton] = {}
        for key, label, tip in QUICK_FILTERS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(key is None)
            b.setObjectName("rychly_filtr")
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, k=key: self.set_quick(k))
            self.quick[key] = b
            qrow.addWidget(b)
        lay.addWidget(chips)
        qrow = QHBoxLayout()
        qrow.setSpacing(4)
        self.b_filter = QPushButton("Filtr ▾")
        self.b_filter.setCheckable(True)
        self.b_filter.setToolTip("Podrobný filtr: typy kontrol, závažnost, vrstva, skrytí opravených")
        qrow.addWidget(self.b_filter)
        self.b_view = QPushButton("▤")
        self.b_view.setFixedWidth(34)
        self.b_view.clicked.connect(lambda: self.set_card_mode(not self.card_mode))
        qrow.addWidget(self.b_view)
        self.b_help = QPushButton("?")
        self.b_help.setToolTip("Co to znamená – vysvětlení vybraného typu chyby s obrázkem (a dalších pojmů)")
        self.b_help.setFixedWidth(34)
        self.b_help.clicked.connect(self.explain)
        qrow.addWidget(self.b_help)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Hledat v popisu, vrstvě, čísle chyby…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filters_changed)
        qrow.insertWidget(0, self.search, 1)
        lay.addLayout(qrow)

        split = QSplitter(Qt.Vertical)
        lay.addWidget(split, 1)

        # ---- filtry
        fbox = QGroupBox("Filtr")
        fl = QVBoxLayout(fbox)
        fl.setContentsMargins(6, 6, 6, 6)
        self.types = QListWidget()
        self.types.setContextMenuPolicy(Qt.CustomContextMenu)
        self.types.customContextMenuRequested.connect(self._types_menu)
        self.types.itemChanged.connect(self._type_toggled)
        self.types.itemDoubleClicked.connect(lambda it: self.only_type(it.data(Qt.UserRole)))
        self.types.setToolTip("Odškrtnutím skryjete kroužky i řádky daného typu. "
                              "Dvojklik nebo pravé tlačítko = jen tento typ.")
        fl.addWidget(self.types, 1)
        row = QHBoxLayout()
        b_only = QPushButton("Jen tento typ")
        b_only.clicked.connect(self._only_current)
        b_all = QPushButton("Zobrazit vše")
        b_all.clicked.connect(self.show_all)
        row.addWidget(b_only)
        row.addWidget(b_all)
        fl.addLayout(row)
        row2 = QHBoxLayout()
        self.sev_boxes: dict[Severity, QCheckBox] = {}
        for s in Severity:
            cb = QCheckBox(s.value)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {SEVERITY_COLORS[s].name()}; font-weight: bold;")
            cb.toggled.connect(self._filters_changed)
            self.sev_boxes[s] = cb
            row2.addWidget(cb)
        row2.addStretch(1)
        fl.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Vrstva:"))
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._filters_changed)
        row3.addWidget(self.layer_combo, 1)
        fl.addLayout(row3)
        self.hide_done = QCheckBox("Skrýt opravené a ignorované")
        self.hide_done.toggled.connect(self._filters_changed)
        fl.addWidget(self.hide_done)
        split.addWidget(fbox)
        self.fbox = fbox
        fbox.setVisible(False)  # rychlé filtry a hledání stačí; podrobný filtr na tlačítko „Filtr“
        self.b_filter.toggled.connect(lambda on: (fbox.setVisible(on),
                                                  self.b_filter.setText("Filtr ▴" if on else "Filtr ▾")))

        # ---- tabulka
        tw = QWidget()
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(0, 0, 0, 0)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self._badges = BadgeDelegate(self.table)
        self.table.setItemDelegateForColumn(C_SEV, self._badges)
        self.table.setItemDelegateForColumn(C_STATE, self._badges)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(False)
        for c, w in enumerate((44, 98, 96, 285, 205, 130, 104, 104)):  # typ kontroly vidět i v užším panelu
            self.table.setColumnWidth(c, w)
        self._cards = CardDelegate(self)
        self.set_card_mode(True)
        self.table.selectionModel().currentRowChanged.connect(self._current_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        tl.addWidget(self.table, 1)

        nav = QHBoxLayout()
        self.b_prev = QPushButton("◀")
        self.b_prev.setFixedWidth(40)
        self.b_prev.setShortcut("F7")
        self.b_prev.setToolTip("Předchozí chyba (F7)")
        self.b_prev.clicked.connect(lambda: self.step(-1))
        self.b_next = QPushButton("▶")
        self.b_next.setFixedWidth(40)
        self.b_next.setShortcut("F8")
        self.b_next.setToolTip("Další chyba (F8)")
        self.b_next.clicked.connect(lambda: self.step(1))
        self.b_fixed = QPushButton("✓ Opraveno")
        self.b_fixed.setToolTip("Označit vybranou chybu jako opravenou a přejít na další (Ctrl+Enter)")
        self.b_fixed.setShortcut("Ctrl+Return")
        self.b_fixed.setProperty("uspech", True)
        self.b_fixed.clicked.connect(lambda: self.set_state("opraveno"))
        self.b_ignore = QPushButton("✕ Ignorovat")
        self.b_ignore.setToolTip("Chybu nebrat v úvahu (např. záměr) a přejít na další (Ctrl+Delete)")
        self.b_ignore.setShortcut("Ctrl+Delete")
        self.b_ignore.clicked.connect(lambda: self.set_state("ignorovat"))
        self.b_new = QPushButton("Vrátit")
        self.b_new.setToolTip("Vrátit stav na „nová“")
        self.b_new.clicked.connect(lambda: self.set_state("nová"))
        for b in (self.b_prev, self.b_next, self.b_fixed, self.b_ignore, self.b_new):
            nav.addWidget(b)
        tl.addLayout(nav)
        self.hint = QLabel()
        self.hint.setObjectName("navod")
        self.hint.setWordWrap(True)
        self.hint.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.hint.linkActivated.connect(lambda h: self.select_issue(int(h)) if h.isdigit() else None)
        self.hint.setVisible(False)
        # návod + obrázek v posuvné oblasti, aby dlouhý text nezmenšil seznam chyb na pár řádků
        from PySide6.QtWidgets import QScrollArea
        self.hint_box = QScrollArea()
        self.hint_box.setObjectName("navod_oblast")
        self.hint_box.setWidgetResizable(True)
        self.hint_box.setFrameShape(QFrame.NoFrame)
        self.hint_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hb = QWidget()
        hb.setObjectName("navod_obsah")
        hl = QVBoxLayout(hb)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        hl.addWidget(self.hint)
        tl.addWidget(self.hint_box)
        # obrázek „jak to má vypadat“ k typu chyby (stejný jako ve vysvětlení „?“)
        self.ilustrace = QLabel()
        self.ilustrace.setObjectName("ilustrace")
        self.ilustrace.setAlignment(Qt.AlignLeft)
        self.ilustrace.setToolTip("Jak to má vypadat – klikněte na „?“ pro celé vysvětlení")
        self.ilustrace.setVisible(False)
        self._ilu_cache: dict[str, object] = {}
        hl.addWidget(self.ilustrace)
        hl.addStretch(1)
        self.hint_box.setWidget(hb)
        self.hint_box.setVisible(False)
        frow = QHBoxLayout()
        self.b_find = QPushButton("Najít v MicroStationu")
        self.b_find.setToolTip("Zkopíruje příkaz, který v MicroStationu vycentruje pohled na místo chyby. "
                               "V MicroStationu otevřete okno Key-in (Nástroje → Key-in), vložte (Ctrl+V) a Enter.")
        self.b_find.clicked.connect(self._copy_keyin)
        self.b_find.setEnabled(False)
        frow.addWidget(self.b_find)
        self.b_copyxy = QPushButton("Kopírovat souřadnice")
        self.b_copyxy.clicked.connect(self._copy_xy)
        self.b_copyxy.setEnabled(False)
        frow.addWidget(self.b_copyxy)
        frow.addStretch(1)
        tl.addLayout(frow)
        self.feature_info = None  # funkce Issue -> text s popisem prvku (nastaví hlavní okno)
        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("Poznámka:"))
        self.note = QLineEdit()
        self.note.setPlaceholderText("Poznámka k vybrané chybě (uloží se do projektu)")
        self.note.setEnabled(False)
        self.note.editingFinished.connect(self._note_edited)
        nrow.addWidget(self.note, 1)
        tl.addLayout(nrow)
        split.addWidget(tw)
        split.setSizes([230, 520])

    # ------------------------------------------------------------ data
    def set_card_mode(self, on: bool):
        """Karty (výchozí, přehledné) nebo tabulka se sloupci (řazení podle sloupců, souřadnice)."""
        self.card_mode = on
        t = self.table
        t.setMouseTracking(on)
        t.setAlternatingRowColors(not on)
        t.horizontalHeader().setVisible(not on)
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtWidgets import QApplication
        t.verticalHeader().setDefaultSectionSize(CardDelegate.height() if on else
                                                 max(30, QFontMetrics(QApplication.font()).height() + 12))
        for c in range(len(COLUMNS)):
            t.setColumnHidden(c, on and c != C_DESC)
        if on:
            t.setItemDelegateForColumn(C_DESC, self._cards)
            t.horizontalHeader().setSectionResizeMode(C_DESC, QHeaderView.Stretch)
            t.setObjectName("karty_chyb")
        else:
            t.setItemDelegateForColumn(C_DESC, None)
            t.horizontalHeader().setSectionResizeMode(C_DESC, QHeaderView.Interactive)
            t.setColumnWidth(C_DESC, 285)
            t.setObjectName("")
        t.style().unpolish(t)
        t.style().polish(t)
        if hasattr(self, "b_view"):
            self.b_view.setText("▤" if on else "☰")
            self.b_view.setToolTip("Přepnout na tabulku se sloupci (řazení, souřadnice)" if on
                                   else "Přepnout na karty")

    NEAR_M = 0.1  # chyby blíž než 10 cm bývají jedna příčina (nepořádek v rohu, dva body na sobě…)
    NEAR_SAME_FEATURE_M = 0.5  # … na stejném prvku i do 50 cm

    @staticmethod
    def _neighbours(issues: list[Issue], r0: float, r1: float = 0.5) -> dict[int, list[int]]:
        r = max(r0, r1)
        cells: dict[tuple[int, int], list[Issue]] = {}
        for i in issues:
            if i.severity != Severity.INFO:
                cells.setdefault((int(i.x // r), int(i.y // r)), []).append(i)
        out: dict[int, list[int]] = {}
        for (cx, cy), lst in cells.items():
            cand = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in cells.get((cx + dx, cy + dy), ())]
            for i in lst:
                # stejný hlavní prvek (první v seznamu) – sdílená sousední čára (např. obrys šrafy) nestačí
                f0 = i.feature_ids[0] if i.feature_ids else None
                near = [j.number for j in cand if j is not i and (
                    (d2 := (j.x - i.x) ** 2 + (j.y - i.y) ** 2) <= r0 * r0
                    or (d2 <= r1 * r1 and f0 is not None and j.feature_ids[:1] == [f0]))]
                if near:
                    out[i.number] = sorted(near)
        return out

    def set_issues(self, issues: list[Issue], summary: str = ""):
        prev_hidden = set(self.proxy.hidden_types)
        self.near = self._neighbours(issues, self.NEAR_M, self.NEAR_SAME_FEATURE_M)
        self._undo = []
        self.model.set_issues(issues)
        n_new = sum(1 for i in issues if i.nove and i.state == "nová")
        b_new = self.quick.get("nove")
        if b_new is not None:  # „★ Nové“ jen když od minulé kontroly něco přibylo
            b_new.setVisible(n_new > 0)
            b_new.setText(f"★ Nové ({n_new})")
            if not n_new and self.proxy.group == "nove":
                self.set_quick(None)
        self._current_changed(QModelIndex(), QModelIndex())  # nový seznam – starý návod a tlačítka pryč
        self._updating = True
        self.types.clear()
        counts = Counter(i.check_name for i in issues)
        sev_of: dict[str, Severity] = {}
        cid_of: dict[str, str] = {}
        for i in issues:
            sev_of.setdefault(i.check_name, i.severity)
            cid_of.setdefault(i.check_name, i.check_id)
        for name in sorted(counts, key=lambda n: (sev_of[n].rank, n)):
            it = QListWidgetItem(f"{name} ({counts[name]})")
            it.setData(Qt.UserRole, name)
            it.setData(Qt.UserRole + 1, cid_of.get(name, ""))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked if name in prev_hidden else Qt.Checked)
            it.setForeground(QBrush(SEVERITY_COLORS.get(sev_of[name])))
            self.types.addItem(it)
        self.proxy.hidden_types = {n for n in prev_hidden if n in counts}
        sev_counts = Counter(i.severity for i in issues)
        for s, cb in self.sev_boxes.items():
            cb.setText(f"{s.value} ({sev_counts.get(s, 0)})")
        cur = self.layer_combo.currentData()
        self.layer_combo.clear()
        self.layer_combo.addItem("Všechny vrstvy", None)
        lc = Counter(i.layer for i in issues)
        for layer in sorted(lc, key=str.lower):
            self.layer_combo.addItem(f"{layer or '(bez vrstvy)'} ({lc[layer]})", layer)
        idx = self.layer_combo.findData(cur)
        self.layer_combo.setCurrentIndex(max(0, idx))
        self._updating = False
        self.summary.setText(summary or self._default_summary(issues))
        self._update_cards()
        self._filters_changed()

    def _default_summary(self, issues: list[Issue]) -> str:
        if not issues:
            return "Zatím žádné nálezy. Otevřete výkres a stiskněte Zkontrolovat (F5)."
        return "Klik na řádek přiblíží chybu, klik na kartu vyfiltruje závažnost."

    def set_score(self, sk):
        """Skóre připravenosti k odevzdání vedle karet (None = zatím nekontrolováno)."""
        if sk is None:
            self.gauge.setVisible(False)
            return
        self.gauge.set_score(sk.hodnota, sk.barva, f"Připravenost k odevzdání: {sk.hodnota}/100 – {sk.popis}"
                             + ("\n" + "\n".join(f"−{s} {co}" for co, s in sk.rozpad) if sk.rozpad else ""))
        self.gauge.setVisible(True)

    def set_banner(self, text: str):
        self.banner.setText(text)
        self.banner.setVisible(bool(text))

    def set_region(self, region):
        """Omezí seznam, kroužky i počty na výřez výkresu (None = celý výkres)."""
        self.proxy.region = region
        self._filters_changed()
        self._update_cards()

    def _update_cards(self):
        issues = [i for i in self.model.issues
                  if self.proxy.region is None or self.proxy.accepts_region(i)]
        open_ = [i for i in issues if i.state == "nová"]
        c = Counter(i.severity for i in open_)
        todo = c.get(Severity.CHYBA, 0) + c.get(Severity.VAROVANI, 0)  # info se neopravuje
        self.cards[None].setText(str(todo))
        done = len(issues) - len(open_)
        self.card_caps[None].setText(f"k opravě (vyřešeno {done} z {len(issues)})" if done else "k opravě")
        for sev in Severity:
            self.cards[sev].setText(str(c.get(sev, 0)))

    def _only_severity(self, sev: Severity):
        self._updating = True
        for s, cb in self.sev_boxes.items():
            cb.setChecked(s == sev)
        self._updating = False
        self._filters_changed()

    def visible_numbers(self) -> set[int]:
        return {i.number for i in self.model.issues if self.proxy.accepts(i)}

    # ------------------------------------------------------------ filtry
    def _type_toggled(self, it: QListWidgetItem):
        if self._updating:
            return
        name = it.data(Qt.UserRole)
        if it.checkState() == Qt.Checked:
            self.proxy.hidden_types.discard(name)
        else:
            self.proxy.hidden_types.add(name)
        self._filters_changed()

    def _filters_changed(self, *_):
        if self._updating:
            return
        self.proxy.severities = {s for s, cb in self.sev_boxes.items() if cb.isChecked()}
        self.proxy.layer = self.layer_combo.currentData()
        self.proxy.hide_done = self.hide_done.isChecked()
        self.proxy.text = self.search.text().strip().lower()
        self.proxy.refresh()
        self.filterChanged.emit(self.visible_numbers())

    def only_type(self, name: str):
        self._updating = True
        for i in range(self.types.count()):
            it = self.types.item(i)
            it.setCheckState(Qt.Checked if it.data(Qt.UserRole) == name else Qt.Unchecked)
        self._updating = False
        self.proxy.hidden_types = {self.types.item(i).data(Qt.UserRole) for i in range(self.types.count())
                                   if self.types.item(i).data(Qt.UserRole) != name}
        self._filters_changed()

    def _only_current(self):
        it = self.types.currentItem()
        if it is None:
            iss = self.current_issue()
            if iss is None:
                return
            self.only_type(iss.check_name)
        else:
            self.only_type(it.data(Qt.UserRole))

    def show_all(self):
        self._updating = True
        for i in range(self.types.count()):
            self.types.item(i).setCheckState(Qt.Checked)
        for cb in self.sev_boxes.values():
            cb.setChecked(True)
        self.layer_combo.setCurrentIndex(0)
        self.hide_done.setChecked(False)
        self.search.clear()
        for k, b in self.quick.items():
            b.setChecked(k is None)
        self.proxy.group = None
        self._updating = False
        self.proxy.hidden_types.clear()
        self._filters_changed()

    def set_quick(self, key):
        """Rychlý filtr nad seznamem: vše / k opravě / topologie / atributy."""
        for k, b in self.quick.items():
            b.setChecked(k == key)
        self.proxy.group = key
        self._filters_changed()

    def explain(self, check_id: str | None = None):
        if not check_id:
            iss = self.current_issue()
            it = self.types.currentItem()
            check_id = iss.check_id if iss else (it.data(Qt.UserRole + 1) if it else None)
        from .help_topics import HelpDialog
        dlg = HelpDialog(self, check_id)
        dlg.exec()

    def _types_menu(self, pos):
        it = self.types.itemAt(pos)
        m = QMenu(self)
        if it is not None:
            m.addAction("Jen tento typ", lambda: self.only_type(it.data(Qt.UserRole)))
            m.addAction("Co to znamená?", lambda: self.explain(it.data(Qt.UserRole + 1)))
        m.addAction("Zobrazit vše", self.show_all)
        m.exec(self.types.mapToGlobal(pos))

    # ------------------------------------------------------------ výběr
    def current_issue(self) -> Issue | None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        return self.model.issues[self.proxy.mapToSource(idx).row()]

    def selected_issues(self) -> list[Issue]:
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        if not rows:
            cur = self.current_issue()
            return [cur] if cur else []
        return [self.model.issues[r] for r in sorted(rows)]

    def _show_illustration(self, check_id: str | None):
        pm = None
        if check_id:
            if check_id not in self._ilu_cache:
                from .help_topics import illustration
                try:
                    self._ilu_cache[check_id] = illustration(check_id, 210)
                except Exception:  # noqa: BLE001 – obrázek je jen pomůcka
                    self._ilu_cache[check_id] = None
            pm = self._ilu_cache[check_id]
        if pm is None:
            self.ilustrace.clear()
            self.ilustrace.setVisible(False)
        else:
            self.ilustrace.setPixmap(pm)
            self.ilustrace.setVisible(True)
        self._fit_hint_box()

    def _fit_hint_box(self):
        vis = not self.hint.isHidden() or not self.ilustrace.isHidden()
        self.hint_box.setVisible(vis)
        if vis:
            need = self.hint_box.widget().sizeHint().height() + 2
            cap = max(120, int(self.height() * 0.26))
            self.hint_box.setFixedHeight(min(need, cap))

    def _current_changed(self, cur, prev):
        if cur.isValid():
            iss = self.model.issues[self.proxy.mapToSource(cur).row()]
            self.note.setEnabled(True)
            self.note.setText(iss.note)
            from ..navody import navod
            h = navod(iss)
            info = self.feature_info(iss) if self.feature_info else ""
            parts = []
            if info:
                parts.append(f"<b>Prvek:</b> {info}")
            if h:
                parts.append(f"<b>Jak opravit:</b> {h}")
            near = self.near.get(iss.number, [])
            if near:
                by_n = {i.number: i for i in self.model.issues}
                from .theme import accent
                links = ", ".join(f"<a href='{n}' style='color:{accent()}'>#{n} {by_n[n].message}</a>"
                                  for n in near[:6] if n in by_n)
                parts.append(f"<b>⧉ Hned vedle</b> jsou další chyby – možná stejná příčina, po opravě často "
                             f"zmizí spolu: {links}" + ("…" if len(near) > 6 else ""))
            self.hint.setText("<br>".join(parts))
            self.hint.setVisible(bool(parts))
            self._show_illustration(iss.check_id)
            self.b_find.setEnabled(True)
            self.b_copyxy.setEnabled(True)
            self.issueSelected.emit(iss.number)
        else:
            self._show_illustration(None)
            self.note.setEnabled(False)
            self.note.clear()
            self.hint.setVisible(False)
            self._fit_hint_box()
            self.b_find.setEnabled(False)
            self.b_copyxy.setEnabled(False)

    def _copy_keyin(self):
        iss = self.current_issue()
        if iss is None:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(f"WINDOW CENTER;XY={iss.x:.3f},{iss.y:.3f}")
        self.message.emit("Zkopírováno. V MicroStationu: Nástroje → Key-in, vložte (Ctrl+V), Enter – pohled se "
                          "vycentruje na místo chyby (pak přibližte kolečkem).")

    def _copy_xy(self):
        iss = self.current_issue()
        if iss is None:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(f"{iss.x:.3f},{iss.y:.3f}")
        self.message.emit(f"Souřadnice zkopírovány: {iss.x:.3f}, {iss.y:.3f}")

    def _note_edited(self):
        iss = self.current_issue()
        if iss is not None and iss.note != self.note.text():
            iss.note = self.note.text()
            self.model.refresh_row(self.model.row_of(iss.number))
            self.stateChanged.emit()

    def select_issue(self, number: int):
        row = self.model.row_of(number)
        if row < 0:
            return
        pidx = self.proxy.mapFromSource(self.model.index(row, 0))
        if not pidx.isValid():
            return
        self.table.selectionModel().setCurrentIndex(
            pidx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self.table.scrollTo(pidx, QAbstractItemView.PositionAtCenter)

    def step(self, delta: int):
        n = self.proxy.rowCount()
        if n == 0:
            return
        cur = self.table.currentIndex()
        r = (cur.row() + delta) % n if cur.isValid() else (0 if delta > 0 else n - 1)
        idx = self.proxy.index(r, 0)
        self.table.selectionModel().setCurrentIndex(
            idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self.table.scrollTo(idx)

    # ------------------------------------------------------------ stav
    def set_state(self, state: str, issues: list[Issue] | None = None):
        sel = self.selected_issues() if issues is None else list(issues)
        if not sel:
            self.message.emit("Nejdřív vyberte chybu v seznamu (klikněte na řádek).")
            return
        changed = False
        before = [(iss, iss.state) for iss in sel if iss.state != state]
        if before:
            self._undo = (self._undo + [before])[-100:]
        for iss in sel:
            if iss.state != state:
                iss.state = state
                self.model.refresh_row(self.model.row_of(iss.number))
                changed = True
        if changed:
            self.stateChanged.emit()
            if self.proxy.hide_done:
                self._filters_changed()
        self._update_cards()
        what = {"opraveno": "označena jako opravená", "ignorovat": "ignorována", "nová": "vrácena k opravě"}[state]
        left = sum(1 for i in self.model.issues if i.state == "nová")
        nums = ", ".join(f"#{i.number}" for i in sel[:5]) + ("…" if len(sel) > 5 else "")
        self.message.emit(f"Chyba {nums} {what}. Zbývá opravit: {left}."
                          + (" (Vrátit: Ctrl+Z)" if issues is not None and len(sel) > 1 else ""))
        if state != "nová" and len(sel) == 1 and issues is None:
            self.next_open()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def undo(self):
        """Vrátí poslední změnu stavu (Opraveno / Ignorovat / Vrátit) a vybere tu chybu."""
        if not self._undo:
            self.message.emit("Není co vracet.")
            return
        last = self._undo.pop()
        for iss, old in last:
            iss.state = old
            self.model.refresh_row(self.model.row_of(iss.number))
        self.stateChanged.emit()
        if self.proxy.hide_done:
            self._filters_changed()
        self._update_cards()
        self.select_issue(last[0][0].number)
        cur = self.current_issue()
        hidden = cur is None or cur.number != last[0][0].number
        nums = ", ".join(f"#{i.number}" for i, _ in last[:5]) + ("…" if len(last) > 5 else "")
        self.message.emit(f"Vráceno zpět: {nums} je znovu „{last[0][1]}“."
                          + (" (Chybu teď skrývá filtr seznamu.)" if hidden else ""))

    def next_open(self):
        """Přejde na další chybu, která ještě není opravená ani ignorovaná."""
        n = self.proxy.rowCount()
        if n == 0:
            return
        cur = self.table.currentIndex()
        start = cur.row() if cur.isValid() else -1
        for k in range(1, n + 1):
            r = (start + k) % n
            iss = self.model.issues[self.proxy.mapToSource(self.proxy.index(r, 0)).row()]
            if iss.state == "nová":
                idx = self.proxy.index(r, 0)
                self.table.selectionModel().setCurrentIndex(
                    idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
                self.table.scrollTo(idx)
                return

    def _table_menu(self, pos):
        m = QMenu(self)
        m.addAction("Označit jako opraveno", lambda: self.set_state("opraveno"))
        m.addAction("Ignorovat", lambda: self.set_state("ignorovat"))
        m.addAction("Vrátit na „nová“", lambda: self.set_state("nová"))
        cur = self.current_issue()
        if cur is not None:  # hromadně – např. všechny „volné konce na okraji“ najednou (Ctrl+Z vrátí)
            same = [i for i in self.model.issues if i.check_id == cur.check_id and i.state == "nová"]
            on_layer = [i for i in self.model.issues if i.layer == cur.layer and i.state == "nová"]
            m.addSeparator()
            if len(same) > 1:
                m.addAction(f"Ignorovat všechny „{cur.check_name}“ ({len(same)})",
                            lambda: self.set_state("ignorovat", same))
            if cur.layer and len(on_layer) > 1:
                m.addAction(f"Ignorovat vše na vrstvě „{cur.layer}“ ({len(on_layer)})",
                            lambda: self.set_state("ignorovat", on_layer))
        m.addSeparator()
        m.addAction("Jen tento typ", self._only_current)
        m.addAction("Zobrazit vše", self.show_all)
        m.addAction("Co to znamená?", self.explain)
        m.exec(self.table.viewport().mapToGlobal(pos))


__all__ = ["IssuePanel", "fmt_coord", "fmt_num"]
