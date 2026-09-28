"""Hlavní okno aplikace."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QLabel, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QTabWidget, QToolBar, QWidget)

from .. import APP_NAME
from ..io.dgn import ConversionError
from ..io.dxf_loader import DrawingLoadError, load_drawing
from ..model import Drawing
from ..project import Project
from .drawing_view import DrawingView
from .layers_panel import LayersPanel
from .worker import BackgroundTask

DRAWING_FILTER = "Výkresy (*.dxf *.dgn *.dwg);;DXF (*.dxf);;DGN (*.dgn);;Všechny soubory (*)"


class MainWindow(QMainWindow):
    def __init__(self, project: Project | None = None):
        super().__init__()
        self.settings = QSettings("KontrolaVykresu", "KontrolaVykresu")
        self.project: Project | None = None
        self.drawing: Drawing | None = None
        self.task: BackgroundTask | None = None
        self.resize(1400, 880)
        self.setAcceptDrops(True)

        self.view = DrawingView()
        self.view.cursorMoved.connect(self._on_cursor)
        self.view.fileDropped.connect(self.open_path)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.view, "Výkres")
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

        m_file = self.menuBar().addMenu("&Soubor")
        m_file.addAction(self.a_open)
        m_file.addSeparator()
        m_file.addAction(self.a_quit)
        m_view = self.menuBar().addMenu("&Zobrazení")
        m_view.addAction(self.a_fit)
        m_view.addAction(self.a_light)
        m_view.addAction(self.layers_dock.toggleViewAction())

        tb = QToolBar("Hlavní panel")
        tb.setObjectName("hlavni_panel")
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addAction(self.a_open)
        tb.addSeparator()
        tb.addAction(self.a_fit)
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
        path = project.drawing_path_for_loading()
        if path is not None:
            self.load_drawing_file(path, add_to_project=False)

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

    def load_drawing_file(self, path: Path, add_to_project: bool = True, after=None):
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
            self.set_drawing(drawing)
            if after:
                after(drawing)

        self._run_task(job, done, f"Načítám {path.name}…", self._load_failed)

    def _load_failed(self, msg: str):
        title = "Výkres nelze otevřít"
        QMessageBox.warning(self, title, msg)

    def set_drawing(self, drawing: Drawing):
        self.drawing = drawing
        self.view.set_drawing(drawing)
        self.layers.set_drawing(drawing)
        n = len(drawing.features)
        self.info_label.setText(f"Načteno {n} prvků, {sum(1 for l in drawing.layers.values() if l.count)} hladin.")
        self._update_title()
        if drawing.warnings:
            self.statusBar().showMessage(f"Upozornění při načítání: {len(drawing.warnings)} "
                                         f"(např. {drawing.warnings[0]})", 15000)

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
