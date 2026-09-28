"""Hlavní okno aplikace."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QLabel, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QSplitter, QTabWidget, QToolBar, QWidget)

from .. import APP_NAME
from ..io.dgn import ConversionError
from ..io.dxf_loader import DrawingLoadError, load_drawing
from ..checks.base import Issue
from ..model import Drawing
from ..project import Project
from ..runner import CheckResult, carry_states, compare, run_checks
from .drawing_view import DrawingView
from .issue_panel import IssuePanel
from .layers_panel import LayersPanel
from .settings_dialog import SettingsDialog
from .worker import BackgroundTask

DRAWING_FILTER = "Výkresy (*.dxf *.dgn *.dwg);;DXF (*.dxf);;DGN (*.dgn);;Všechny soubory (*)"


class MainWindow(QMainWindow):
    def __init__(self, project: Project | None = None):
        super().__init__()
        self.settings = QSettings("KontrolaVykresu", "KontrolaVykresu")
        self.project: Project | None = None
        self.drawing: Drawing | None = None
        self.task: BackgroundTask | None = None
        self.issues: list[Issue] = []
        self.resize(1400, 880)
        self.setAcceptDrops(True)

        self.view = DrawingView()
        self.view.cursorMoved.connect(self._on_cursor)
        self.view.fileDropped.connect(self.open_path)

        self.view.markerClicked.connect(self._on_marker_clicked)

        self.issue_panel = IssuePanel()
        self.issue_panel.issueSelected.connect(self._on_issue_selected)
        self.issue_panel.filterChanged.connect(self.view.set_visible_issues)
        self.issue_panel.stateChanged.connect(self._on_states_changed)

        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self.view)
        self.split.addWidget(self.issue_panel)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        self.split.setSizes([860, 540])

        self.tabs = QTabWidget()
        self.tabs.addTab(self.split, "Výkres a chyby")
        self.setCentralWidget(self.tabs)

        self.layers = LayersPanel()
        self.layers.layerToggled.connect(self.view.set_layer_visible)
        self.layers_dock = QDockWidget("Hladiny", self)
        self.layers_dock.setObjectName("hladiny")
        self.layers_dock.setWidget(self.layers)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.layers_dock)

        self._build_status()
        self._build_actions()
        self._restore_geometry()
        if project is not None:
            self.set_project(project)
        else:
            self._open_last_project()

    # ------------------------------------------------------------------ UI
    def _build_status(self):
        sb = self.statusBar()
        self.coord_label = QLabel("X: –   Y: –")
        self.coord_label.setMinimumWidth(260)
        self.info_label = QLabel("")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.setVisible(False)
        self.cancel_btn = QPushButton("Zrušit")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_task)
        sb.addWidget(self.info_label, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.cancel_btn)
        sb.addPermanentWidget(self.coord_label)

    def _act(self, text, slot, shortcut=None, tip=None, checkable=False) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        return a

    def _build_actions(self):
        self.a_open = self._act("Otevřít výkres…", self.open_dialog, "Ctrl+O",
                                "Otevřít výkres DXF (nebo DGN přes ODA File Converter)")
        self.a_fit = self._act("Přiblížit vše", self.view.fit_all, "Home", "Zobrazit celý výkres")
        self.a_light = self._act("Světlé pozadí", self.view.set_light_background, None,
                                 "Přepnout černé/bílé pozadí výkresu", checkable=True)
        self.a_quit = self._act("Konec", self.close, "Ctrl+Q")
        self.a_check = self._act("Zkontrolovat", self.run_checks, "F5", "Spustit zapnuté kontroly")
        self.a_recheck = self._act("Zkontrolovat znovu", self.recheck, "Ctrl+F5",
                                   "Znovu načíst výkres ze souboru, zkontrolovat a porovnat počet chyb")
        self.a_settings = self._act("Nastavení kontrol…", self.edit_settings, "Ctrl+,",
                                    "Tolerance, zapnutí/vypnutí kontrol a jejich závažnost")
        self.a_labels = self._act("Popisky chyb", self.view.set_labels_visible, "Ctrl+L",
                                  "Zobrazit/skrýt popisky u kroužků chyb", checkable=True)
        self.a_labels.setChecked(True)
        self.a_prev = self._act("◀ Předchozí chyba", lambda: self.issue_panel.step(-1), None,
                                "Předchozí chyba (F7)")
        self.a_next = self._act("Další chyba ▶", lambda: self.issue_panel.step(1), None, "Další chyba (F8)")

        m_file = self.menuBar().addMenu("&Soubor")
        m_file.addAction(self.a_open)
        m_file.addSeparator()
        m_file.addAction(self.a_quit)
        m_view = self.menuBar().addMenu("&Zobrazení")
        m_view.addAction(self.a_fit)
        m_view.addAction(self.a_light)
        m_view.addAction(self.a_labels)
        m_view.addAction(self.layers_dock.toggleViewAction())
        m_check = self.menuBar().addMenu("&Kontrola")
        m_check.addAction(self.a_check)
        m_check.addAction(self.a_recheck)
        m_check.addSeparator()
        m_check.addAction(self.a_settings)

        tb = QToolBar("Hlavní panel")
        tb.setObjectName("hlavni_panel")
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addAction(self.a_open)
        tb.addSeparator()
        tb.addAction(self.a_check)
        tb.addAction(self.a_recheck)
        tb.addAction(self.a_settings)
        tb.addSeparator()
        tb.addAction(self.a_fit)
        tb.addAction(self.a_labels)
        tb.addAction(self.a_prev)
        tb.addAction(self.a_next)
        self.addToolBar(tb)
        self.toolbar = tb

    def _restore_geometry(self):
        g = self.settings.value("okno/geometrie")
        if g is not None:
            self.restoreGeometry(g)
        s = self.settings.value("okno/stav")
        if s is not None:
            self.restoreState(s)
        light = self.settings.value("zobrazeni/svetle_pozadi", False, type=bool)
        self.a_light.setChecked(light)

    def closeEvent(self, event):  # noqa: N802
        if self.task is not None and self.task.is_running():
            self.task.cancel()
        self.settings.setValue("okno/geometrie", self.saveGeometry())
        self.settings.setValue("okno/stav", self.saveState())
        self.settings.setValue("zobrazeni/svetle_pozadi", self.a_light.isChecked())
        if self.project is not None:
            try:
                self.project.save()
            except OSError:
                pass
        super().closeEvent(event)

    # ------------------------------------------------------------------ projekt
    def _open_last_project(self):
        last = self.settings.value("projekt/posledni", "")
        project = None
        if last:
            try:
                project = Project.open(last)
            except (OSError, FileNotFoundError, ValueError):
                project = None
        if project is None:
            project = Project.new_in_default_location("Můj projekt")
        self.set_project(project)

    def set_project(self, project: Project):
        self.project = project
        self.settings.setValue("projekt/posledni", str(project.root))
        self._update_title()
        self.set_issues([])
        path = project.drawing_path_for_loading()
        if path is not None:
            stored = project.load_issues()
            self.load_drawing_file(path, add_to_project=False,
                                   after=(lambda d: self.set_issues(stored, "Výsledek poslední kontroly "
                                                                    "(pro aktuální stav spusťte kontrolu).")
                                          ) if stored else None)

    def _update_title(self):
        parts = [APP_NAME]
        if self.project is not None:
            parts.insert(0, self.project.name)
        if self.drawing is not None:
            parts.insert(0, Path(self.drawing.source_path or self.drawing.path).name)
        self.setWindowTitle(" – ".join(parts))

    # ------------------------------------------------------------------ výkres
    def open_dialog(self):
        start = self.settings.value("cesty/vykres", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, "Otevřít výkres", start, DRAWING_FILTER)
        if path:
            self.settings.setValue("cesty/vykres", str(Path(path).parent))
            self.open_path(path)

    def open_path(self, path: str):
        """Otevře soubor přetažený do okna nebo vybraný v dialogu."""
        suffix = Path(path).suffix.lower()
        if suffix in (".dxf", ".dgn", ".dwg"):
            self.load_drawing_file(Path(path), add_to_project=True)
        else:
            QMessageBox.information(self, APP_NAME,
                                    f"Soubor {Path(path).name} není výkres. Podklady (tabulky, náčrty, "
                                    f"fotky) přidejte na záložce Zadání.")

    def load_drawing_file(self, path: Path, add_to_project: bool = True, after=None, keep_view=False):
        if self.task is not None and self.task.is_running():
            QMessageBox.information(self, APP_NAME, "Počkejte na dokončení probíhající úlohy.")
            return
        oda = self.project.config.oda_cesta if self.project else None

        def job(progress, cancelled):
            return load_drawing(path, progress, oda)

        def done(drawing: Drawing):
            if add_to_project and self.project is not None:
                try:
                    self.project.set_drawing(path)
                    self.project.save()
                except OSError as exc:
                    QMessageBox.warning(self, APP_NAME, f"Výkres se nepodařilo zkopírovat do projektu: {exc}")
            self.set_drawing(drawing, keep_view=keep_view)
            if after:
                after(drawing)

        self._run_task(job, done, f"Načítám {path.name}…", self._load_failed)

    def _load_failed(self, msg: str):
        title = "Výkres nelze otevřít"
        QMessageBox.warning(self, title, msg)

    def set_drawing(self, drawing: Drawing, keep_view: bool = False):
        self.drawing = drawing
        tr, center = self.view.transform(), self.view.mapToScene(self.view.viewport().rect().center())
        self.view.set_drawing(drawing)
        if keep_view:
            self.view.setTransform(tr)
            self.view.centerOn(center)
        self.layers.set_drawing(drawing)
        self.set_issues([])
        n = len(drawing.features)
        self.info_label.setText(f"Načteno {n} prvků, {sum(1 for l in drawing.layers.values() if l.count)} hladin.")
        self._update_title()
        if drawing.warnings:
            self.statusBar().showMessage(f"Upozornění při načítání: {len(drawing.warnings)} "
                                         f"(např. {drawing.warnings[0]})", 15000)

    # ------------------------------------------------------------------ kontroly
    def run_checks(self, after=None):
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres (tlačítko Otevřít výkres "
                                                    "nebo přetažením souboru do okna).")
            return
        if self.task is not None and self.task.is_running():
            return
        drawing, rules, config = self.drawing, self.project.rules, self.project.config

        def job(progress, cancelled):
            return run_checks(drawing, rules, config, progress, cancelled)

        self._run_task(job, lambda res: self._checks_done(res, after), "Spouštím kontroly…")

    def _checks_done(self, res: CheckResult, after=None):
        if res.cancelled:
            self.info_label.setText("Kontrola byla zrušena.")
            return
        carry_states(self.project.issue_states(), res.issues, recheck=after is not None)
        summary = None
        if after is not None:
            summary = after(res)
        self.set_issues(res.issues, summary)
        self.project.store_issues(res.issues)
        self.project.save()
        if res.notes:
            self.statusBar().showMessage(" | ".join(res.notes[:4]), 20000)
        self.last_notes = res.notes

    def recheck(self):
        if self.project is None:
            return
        path = self.project.drawing_path_for_loading()
        if path is None:
            self.run_checks()
            return
        old = list(self.issues)

        def compare_text(res: CheckResult) -> str:
            cmp = compare(old, res.issues)
            msg = (f"Opakovaná kontrola: {len(res.issues)} problémů (předtím {len(old)}). {cmp.text()}")
            QMessageBox.information(self, "Zkontrolovat znovu", msg)
            return msg

        self.project.refresh_drawing_copy()
        self.load_drawing_file(path, add_to_project=False, keep_view=True,
                               after=lambda d: self.run_checks(after=compare_text))

    def set_issues(self, issues: list[Issue], summary: str | None = None):
        self.issues = issues
        self.view.set_issues(issues)
        self.issue_panel.set_issues(issues, summary or "")

    def edit_settings(self):
        dlg = SettingsDialog(self.project.config, self.project.rules, self)
        if dlg.exec():
            self.project.config = dlg.result_config()
            dlg.apply_rules_settings(self.project.rules)
            self.project.save()

    def _on_issue_selected(self, number: int):
        self.view.highlight_issue(number, zoom=True)

    def _on_marker_clicked(self, number: int):
        self.issue_panel.select_issue(number)
        self.view.highlight_issue(number, zoom=False)

    def _on_states_changed(self):
        self.view.refresh_markers()
        if self.project is not None:
            self.project.store_issues(self.issues)
            self.project.save()

    # ------------------------------------------------------------------ úlohy na pozadí
    def _run_task(self, fn, on_done, text: str, on_fail=None):
        self.task = BackgroundTask(fn, self)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.info_label.setText(text)

        def prog(p, msg):
            self.progress.setValue(p)
            if msg:
                self.info_label.setText(msg)

        def fin(result):
            self.progress.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.task = None
            on_done(result)

        def fail(msg):
            self.progress.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.task = None
            self.info_label.setText("")
            (on_fail or (lambda m: QMessageBox.warning(self, APP_NAME, m)))(msg)

        self.task.progress.connect(prog)
        self.task.finished.connect(fin)
        self.task.failed.connect(fail)
        self.task.start()

    def _cancel_task(self):
        if self.task is not None:
            self.task.cancel()
            self.info_label.setText("Ruším…")

    # ------------------------------------------------------------------ události
    def _on_cursor(self, x: float, y: float):
        self.coord_label.setText(f"X: {x:,.3f}   Y: {y:,.3f}".replace(",", " ").replace(".", ","))

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())
                break
