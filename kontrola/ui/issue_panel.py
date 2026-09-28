"""Panel se seznamem chyb, filtry a tlačítky pro procházení."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import (QAbstractTableModel, QItemSelectionModel, QModelIndex, QSortFilterProxyModel,
                            Qt, Signal)
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QPushButton, QSplitter, QTableView, QVBoxLayout, QWidget)

from ..checks.base import ISSUE_STATES, Issue, Severity, fmt_num
from .drawing_view import SEVERITY_COLORS

COLUMNS = ["Č.", "Závažnost", "Stav", "Popis", "Typ kontroly", "Hladina", "X", "Y"]
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
            return [str(iss.number), iss.severity.value, STATE_LABEL.get(iss.state, iss.state), iss.message,
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
                return QBrush(QColor(107, 114, 128))
        if role == Qt.FontRole and done:
            f = QFont()
            if c == C_STATE:
                f.setBold(True)
            elif c in (C_DESC, C_TYPE):
                f.setStrikeOut(True)
            return f
        if role == Qt.BackgroundRole and iss.state == "opraveno":
            return QBrush(QColor(236, 253, 243))
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


class IssueFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hidden_types: set[str] = set()
        self.severities: set[Severity] = set(Severity)
        self.layer: str | None = None
        self.region: tuple[float, float, float, float] | None = None  # jen chyby v tomto výřezu
        self.hide_done = False
        self.text = ""
        self.setSortRole(Qt.UserRole)

    def filterAcceptsRow(self, row, parent):  # noqa: N802
        iss: Issue = self.sourceModel().issues[row]
        return self.accepts(iss)

    def accepts(self, iss: Issue) -> bool:
        if iss.check_name in self.hidden_types:
            return False
        if iss.severity not in self.severities:
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
        for key, title, color in ((None, "k opravě", "#1F2937"),
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
        lay.addLayout(cards)
        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        lay.addWidget(self.banner)
        self.summary = QLabel("Zatím neproběhla žádná kontrola. Otevřete výkres a stiskněte Zkontrolovat (F5).")
        self.summary.setObjectName("souhrn")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

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
        row3.addWidget(QLabel("Hladina:"))
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._filters_changed)
        row3.addWidget(self.layer_combo, 1)
        fl.addLayout(row3)
        self.hide_done = QCheckBox("Skrýt opravené a ignorované")
        self.hide_done.toggled.connect(self._filters_changed)
        fl.addWidget(self.hide_done)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat v popisu, hladině, čísle chyby…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filters_changed)
        fl.addWidget(self.search)
        split.addWidget(fbox)

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
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(False)
        for c, w in enumerate((46, 100, 118, 380, 170, 150, 110, 110)):
            self.table.setColumnWidth(c, w)
        self.table.selectionModel().currentRowChanged.connect(self._current_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        tl.addWidget(self.table, 1)

        nav = QHBoxLayout()
        self.b_prev = QPushButton("◀ Předchozí")
        self.b_prev.setShortcut("F7")
        self.b_prev.setToolTip("Předchozí chyba (F7)")
        self.b_prev.clicked.connect(lambda: self.step(-1))
        self.b_next = QPushButton("Další ▶")
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
        self.hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hint.setVisible(False)
        tl.addWidget(self.hint)
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
    def set_issues(self, issues: list[Issue], summary: str = ""):
        prev_hidden = set(self.proxy.hidden_types)
        self.model.set_issues(issues)
        self._updating = True
        self.types.clear()
        counts = Counter(i.check_name for i in issues)
        sev_of: dict[str, Severity] = {}
        for i in issues:
            sev_of.setdefault(i.check_name, i.severity)
        for name in sorted(counts, key=lambda n: (sev_of[n].rank, n)):
            it = QListWidgetItem(f"{name} ({counts[name]})")
            it.setData(Qt.UserRole, name)
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
        self.layer_combo.addItem("Všechny hladiny", None)
        lc = Counter(i.layer for i in issues)
        for layer in sorted(lc, key=str.lower):
            self.layer_combo.addItem(f"{layer or '(bez hladiny)'} ({lc[layer]})", layer)
        idx = self.layer_combo.findData(cur)
        self.layer_combo.setCurrentIndex(max(0, idx))
        self._updating = False
        self.summary.setText(summary or self._default_summary(issues))
        self._update_cards()
        self._filters_changed()

    def _default_summary(self, issues: list[Issue]) -> str:
        if not issues:
            return "Zatím žádné nálezy. Otevřete výkres a stiskněte Zkontrolovat (F5)."
        return "Kliknutím na řádek se výkres přiblíží na chybu. Kliknutím na kartu nahoře vyfiltrujete závažnost."

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
        self.cards[None].setText(str(len(open_)))
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
        self._updating = False
        self.proxy.hidden_types.clear()
        self._filters_changed()

    def _types_menu(self, pos):
        it = self.types.itemAt(pos)
        m = QMenu(self)
        if it is not None:
            m.addAction("Jen tento typ", lambda: self.only_type(it.data(Qt.UserRole)))
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

    def _current_changed(self, cur, prev):
        if cur.isValid():
            iss = self.model.issues[self.proxy.mapToSource(cur).row()]
            self.note.setEnabled(True)
            self.note.setText(iss.note)
            from ..navody import navod
            h = navod(iss)
            self.hint.setText(f"<b>Jak opravit:</b> {h}" if h else "")
            self.hint.setVisible(bool(h))
            self.issueSelected.emit(iss.number)
        else:
            self.note.setEnabled(False)
            self.note.clear()
            self.hint.setVisible(False)

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
    def set_state(self, state: str):
        sel = self.selected_issues()
        if not sel:
            self.message.emit("Nejdřív vyberte chybu v seznamu (klikněte na řádek).")
            return
        changed = False
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
        self.message.emit(f"Chyba {nums} {what}. Zbývá opravit: {left}.")
        if state != "nová" and len(sel) == 1:
            self.next_open()

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
        m.addSeparator()
        m.addAction("Jen tento typ", self._only_current)
        m.addAction("Zobrazit vše", self.show_all)
        m.exec(self.table.viewport().mapToGlobal(pos))


__all__ = ["IssuePanel", "fmt_coord", "fmt_num"]
