"""Hlavní okno aplikace."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSizePolicy, QTabWidget, QToolBar, QToolButton, QWidget)

from .. import APP_NAME
from ..checks.base import Issue, Severity
from ..io.dgn import DGN_NAVOD, JINE_PROGRAMY_NAVOD
from ..io.dxf_loader import load_drawing
from ..model import Drawing
from ..project import PROJECT_EXT, Project, default_projects_dir
from ..runner import CheckResult, carry_states, compare, run_checks
from .drawing_view import DrawingView, prepare_drawing
from .image_viewer import ImageBrowser, load_pixmap
from .issue_panel import IssuePanel
from .layers_panel import LayersPanel
from .settings_dialog import SettingsDialog
from .worker import BackgroundTask
from .zadani_tab import ZadaniTab

DRAWING_FILTER = ("Výkresy (*.dxf *.dgn *.dwg *.vfk *.shp *.geojson);;DXF (*.dxf);;DGN (*.dgn);;"
                  "VFK – katastr (*.vfk);;GIS – Shapefile, GeoJSON (*.shp *.geojson *.json);;Všechny soubory (*)")


class MainWindow(QMainWindow):
    _updateResult = Signal(object, str, bool)  # výsledek kontroly aktualizací z vlákna na pozadí

    def __init__(self, project: Project | None = None):
        super().__init__()
        self._updateResult.connect(self._on_update_result)
        self.settings = QSettings("KontrolaVykresu", "KontrolaVykresu")
        self.project: Project | None = None
        self.drawing: Drawing | None = None
        self.prev_drawing: Drawing | None = None  # předchozí načtená verze (porovnání verzí)
        self.task: BackgroundTask | None = None
        self.issues: list[Issue] = []
        self._syncing_wip = False
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
        self.issue_panel.message.connect(lambda t: self.statusBar().showMessage(t, 8000))
        self.issue_panel.feature_info = self._feature_info

        from .canvas import Canvas
        # výkres přes celou plochu, seznam chyb jako plovoucí (sbalitelná) karta vpravo
        self.split = Canvas(self.view, self.issue_panel)

        self.zadani = ZadaniTab(lambda: self.drawing)
        self.zadani.rulesChanged.connect(self._rules_changed)
        self.zadani.projectModified.connect(self._project_modified)
        self.zadani.backgroundChanged.connect(self._apply_background)
        self.zadani.showSketchBeside.connect(self.show_sketch_beside)
        self.zadani.georefRequested.connect(self.start_georef)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("hlavni_zalozky")
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.split, "Výkres a chyby")
        self.tabs.addTab(self.zadani, "Zadání")
        from .vypocty_page import VypoctyPage
        self.vypocty = VypoctyPage(self)
        self.tabs.addTab(self.vypocty, "Výpočty")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        self.layers = LayersPanel()
        self.layers.layerToggled.connect(self.view.set_layer_visible)
        self.layers_dock = QDockWidget("Vrstvy", self)
        self.layers_dock.setObjectName("hladiny")
        self.layers_dock.setWidget(self.layers)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.layers_dock)

        from .inspector import InspectorPanel
        self.inspector = InspectorPanel()
        self.inspector_dock = QDockWidget("Prvek", self)
        self.inspector_dock.setObjectName("prvek")
        self.inspector_dock.setWidget(self.inspector)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.inspector_dock)
        self.tabifyDockWidget(self.layers_dock, self.inspector_dock)
        self.layers_dock.raise_()
        self.view.featureClicked.connect(self._on_feature_clicked)

        self.sketch = ImageBrowser(compact=True)
        self.sketch.noteChanged.connect(self._sketch_note_changed)
        self.zadani.noteChangedSignal.connect(self.sketch.sync_note)
        self.sketch_dock = QDockWidget("Náčrt a fotky", self)
        self.sketch_dock.setObjectName("nacrt")
        self.sketch_dock.setWidget(self.sketch)
        self.sketch_dock.setToolTip("Panel lze odpojit do plovoucího okna tlačítkem v jeho záhlaví.")
        self.addDockWidget(Qt.RightDockWidgetArea, self.sketch_dock)
        from .poradce import PoradcePanel
        self.poradce = PoradcePanel(win=self)
        self.poradce_dock = QDockWidget("Poradce", self)
        self.poradce_dock.setObjectName("poradce")
        self.poradce_dock.setWidget(self.poradce)
        self.addDockWidget(Qt.RightDockWidgetArea, self.poradce_dock)
        self.poradce_dock.hide()
        self.sketch_dock.hide()

        self._build_status()
        self._build_actions()
        from .home_page import HomePage
        self.home = HomePage(self)
        self.home.openRecent.connect(self.open_path)
        self.tabs.insertTab(0, self.home, "Úvod")
        self.tabs.setCurrentWidget(self.home)
        self.tabs.setIconSize(QSize(18, 18))
        self._apply_icons()
        self._init_watch()
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
        self.watch_label = QLabel("")
        self.watch_label.setToolTip("Po uložení výkresu (v MicroStationu Uložit jako DXF) se výkres sám "
                                    "zkontroluje znovu. Vypnutí: Kontrola → Hlídat změny výkresu.")
        sb.addPermanentWidget(self.watch_label)
        sb.addPermanentWidget(self.coord_label)

    def _act(self, text, slot, shortcut=None, tip=None, checkable=False) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.setCheckable(checkable)
        from .crash import step
        if checkable:
            # jen kliknutí uživatele (triggered), ne nastavení volby při startu (toggled)
            a.triggered.connect(lambda on, t=text: step(f"{t}: {'zapnuto' if on else 'vypnuto'}"))
            a.toggled.connect(slot)
        else:
            # triggered(bool) by jinak předal „checked“ jako první argument (např. run_checks(after=False))
            a.triggered.connect(lambda _checked=False, s=slot, t=text: (step(t), s()))
        return a

    def _build_actions(self):
        self.a_open = self._act("Otevřít výkres…", self.open_dialog, "Ctrl+O",
                                "Otevřít výkres DXF (nebo DGN přes ODA File Converter)")
        self.a_fit = self._act("Přiblížit vše", self.view.fit_all, "Home", "Zobrazit celý výkres")
        self.a_light = self._act("Světlé pozadí", self.view.set_light_background, None,
                                 "Přepnout černé/bílé pozadí výkresu", checkable=True)
        self.a_mslook = self._act("Styly a tloušťky čar jako v MicroStationu", self.view.set_ms_look, None,
                                  "Čárkování, tloušťky a značky uživatelských stylů (ploty…). Vypnuto = tenké "
                                  "plné čáry.", checkable=True)
        self.a_dark = self._act("Tmavý režim", self.set_dark, None, "Tmavé barvy oken (šetří oči večer)",
                                checkable=True)
        self.a_quit = self._act("Konec", self.close, "Ctrl+Q")
        self.a_check = self._act("Zkontrolovat", self.run_checks, "F5", "Spustit zapnuté kontroly")
        self.a_vyber = self._act("Co zkontrolovat…", self.show_check_selection, "Ctrl+Shift+K",
                                 "Zaškrtnout, které kontroly se mají spustit (i hotové sady: jako učitel, vše…)")
        self.a_recheck = self._act("Zkontrolovat znovu", self.recheck, "Ctrl+F5",
                                   "Znovu načíst výkres ze souboru, zkontrolovat a porovnat počet chyb")
        self.a_repair = self._act("Automatická oprava…", self.repair, "Ctrl+R",
                                  "Opravit duplicity, nedotažení, přetažení, uzly a téměř uzavřené polygony "
                                  "do nového DXF (jako režim oprava v MGEO)")
        self.a_settings = self._act("Nastavení kontrol…", self.edit_settings, "Ctrl+,",
                                    "Tolerance, zapnutí/vypnutí kontrol a jejich závažnost")
        self.a_labels = self._act("Popisky chyb", self.view.set_labels_visible, "Ctrl+L",
                                  "Zobrazit/skrýt popisky u kroužků chyb", checkable=True)
        self.a_labels.setChecked(True)
        self.a_labels.setIconText("Popisky")
        self.a_prev = self._act("◀ Předchozí chyba", lambda: self.issue_panel.step(-1), None,
                                "Předchozí chyba (F7)")
        self.a_next = self._act("Další chyba ▶", lambda: self.issue_panel.step(1), None, "Další chyba (F8)")
        self.a_new_project = self._act("Nový projekt…", self.new_project, "Ctrl+N")
        self.a_open_project = self._act("Otevřít projekt…", self.open_project_dialog, "Ctrl+Shift+O",
                                        "Otevřít projekt ze souboru .kontrola nebo ze složky")
        self.a_save_project = self._act("Uložit projekt", self.save_project, "Ctrl+S")
        self.a_save_project_as = self._act("Uložit projekt jako soubor .kontrola…", self.save_project_as,
                                           "Ctrl+Shift+S", "Celý projekt (výkres, pravidla, podklady, stav "
                                           "chyb) do jednoho souboru")
        self.a_exp_csv = self._act("Seznam chyb do CSV…", lambda: self.export("csv"))
        self.a_exp_xlsx = self._act("Seznam chyb do Excelu…", lambda: self.export("xlsx"))
        self.a_exp_pdf = self._act("Protokol do PDF…", lambda: self.export("pdf"))
        self.a_exp_todo = self._act("Seznam k opravě na tisk (PDF)…", lambda: self.export("todo"), "Ctrl+P",
                                    "Chyby k opravě seskupené podle typu, s políčkem k odškrtnutí, návodem "
                                    "a výřezem – vytisknout a mít vedle MicroStationu")
        self.a_exp_html = self._act("Interaktivní protokol (HTML)…", lambda: self.export("html"), None,
                                    "Jeden soubor pro prohlížeč: přehledka s kroužky, filtr, návody a výřezy")
        self.a_exp_dxf = self._act("DXF s vrstvou KONTROLA_CHYBY…", lambda: self.export("dxf"))
        self.a_exp_log = self._act("Protokol jako MGEO / GISoft (.log)…", lambda: self.export("log"))
        self.a_print_preview = self._act("Náhled tisku v měřítku (PDF)…", self.print_preview, None,
                                         "Mapa do PDF přesně v měřítku (1:500…) s tloušťkami čar jako na tisku")
        self.a_wip = self._act("Rozpracovaný výkres", self._toggle_wip, None,
                               "Výkres ještě není hotový: nehlásit volné konce, neuzavřené plochy, mezery mezi "
                               "plochami a chybějící popisy. Nakreslené prvky se kontrolují dál. Před odevzdáním "
                               "vypněte.", checkable=True)
        self.a_region = self._act("Jen tento výřez", self._toggle_region, None,
                                  "Počítat jen chyby v právě zobrazené části výkresu (přibližte si hotovou část). "
                                  "Opětovným kliknutím se vrátíte k celému výkresu.", checkable=True)
        self.a_watch = self._act("Hlídat změny výkresu", self._toggle_watch, None,
                                 "Když výkres znovu uložíte (v MicroStationu Uložit jako DXF), aplikace ho sama "
                                 "načte a zkontroluje.", checkable=True)
        self.a_ms_send = self._act("Posílat chyby do MicroStationu", self._toggle_ms_send, None,
                                   "Po každé kontrole uloží vedle výkresu <název>_chyby.txt pro makro v MicroStationu",
                                   checkable=True)
        self.a_ms_help = self._act("Propojení s MicroStationem (makro)…", self.show_ms_link, None,
                                   "Chyby jako dočasné kroužky přímo v MicroStationu, F8 = další chyba")
        self.a_ready = self._act("Připraveno k odevzdání?", self.ready_check, None,
                                 "Úplná kontrola jako před odevzdáním (s tolerancemi učitele), semafor, co zbývá "
                                 "opravit, počítadlo odevzdání a průběh chyb v čase")
        self.a_seznam = self._act("Ověřit seznam souřadnic…", self.verify_list, "Ctrl+J",
                                  "Sedí body ve výkresu na seznam souřadnic? (poloha, čísla, výšky, body navíc)")
        self.a_notify = self._act("Upozornění Windows po uložení výkresu", self._set_notify, None,
                                  "Když hlídáte výkres a uložíte ho v MicroStationu, vpravo dole se ukáže, kolik "
                                  "chyb ubylo a kolik zbývá", checkable=True)
        self.a_notify.setChecked(self.settings.value("upozorneni/zapnuto", True, type=bool))
        self.a_undo = self._act("Zpět", self.undo_dispatch, "Ctrl+Z",
                                "Vrátí poslední krok: na stránce Výpočty změnu seznamu bodů, jinak Opraveno / "
                                "Ignorovat u chyby")
        self.a_redo = self._act("Znovu", self.redo_dispatch, "Ctrl+Y", "Znovu provede vrácený krok (Výpočty)")
        self.a_heat = self._act("Tepelná mapa chyb", self.view.set_heatmap, "Ctrl+Shift+H",
                                "Barevně ukáže, kde je ve výkrese nejvíc neopravených chyb", checkable=True)
        self.a_focus = self._act("Režim soustředění", self.set_focus_mode, "F11",
                                 "Jen výkres a jedna chyba velkým písmem – Opraveno / Další, Esc ukončí",
                                 checkable=True)
        self.a_mini = self._act("Okno „Další chyba“ navrchu", self.show_mini, "Ctrl+Shift+N",
                                "Malé okno, které zůstane nad MicroStationem: popis chyby, key-in, Opraveno/Další")
        self.a_fixguide = self._act("Opravný průvodce (MicroStation)…", self.show_fix_guide, "Ctrl+G",
                                    "Chyby jedna po druhé s přesným postupem a souřadnicemi pro MicroStation")
        self.a_predikce = self._act("Učitelův pohled – předpověď protokolu…", self.show_prediction, None,
                                    "Co nejspíš nahlásí učitel (naučeno z jeho dřívějších protokolů) + náhled "
                                    "protokolu v jeho formátu")
        self.a_prehled = self._act("Přehled výkresu…", self.show_overview, "Ctrl+Shift+P",
                                   "Co je na které vrstvě: počty prvků, barvy, styly, tloušťky, písmo, délky")
        self.a_timeline = self._act("Časová osa výkresu…", self.show_timeline, "Ctrl+H",
                                    "Všechny uložené verze výkresu: přehrát, porovnat, vytáhnout smazané prvky")
        self.a_spojnice = self._act("Spojnice podle náčrtu…", self.verify_lines, None,
                                    "Je nakreslené všechno, co je v náčrtu spojené? (plot 1-2-3…)")
        self.a_batch = self._act("Zkontrolovat více výkresů najednou…", self.batch_check, None,
                                 "Vyberte několik DXF (třeba celou složku) – souhrnná tabulka chyb a skóre")
        self.a_compare = self._act("Porovnat verze výkresu…", self.compare_versions, "Ctrl+D",
                                   "Co se změnilo od předchozí načtené verze (nebo proti jinému DXF): "
                                   "přidané, odebrané a upravené prvky barevně ve výkresu")
        self.a_teacher = self._act("Porovnat s protokolem učitele…", self.compare_teacher, None,
                                   "Načíst protokol od učitele (GISoft / MGEO .log) a porovnat s nálezy programu")
        self.a_vypocet = self._act("Kontrola výpočtu souřadnic (zápisník)…", self.show_vypocet, None,
                                   "Spočítat body ze zápisníku totální stanice a porovnat s vaším seznamem z Gromy")
        self.a_sketch = self._act("Náčrt vedle výkresu", self.show_sketch_beside, "Ctrl+B",
                                  "Zobrazit náčrt a fotky v panelu vedle výkresu (panel lze odpojit)")

        m_file = self.menuBar().addMenu("&Soubor")
        m_file.addAction(self.a_open)
        self.m_recent = m_file.addMenu("Naposledy otevřené výkresy")
        self.m_recent.aboutToShow.connect(self._fill_recent)
        m_file.addSeparator()
        m_file.addAction(self.a_new_project)
        m_file.addAction(self.a_open_project)
        m_file.addAction(self.a_save_project)
        m_file.addAction(self.a_save_project_as)
        m_file.addSeparator()
        m_exp = m_file.addMenu("Export")
        for a in (self.a_exp_html, self.a_exp_pdf, self.a_exp_todo, self.a_exp_csv, self.a_exp_xlsx, self.a_exp_dxf,
                  self.a_exp_log, self.a_print_preview):
            m_exp.addAction(a)
        m_file.addSeparator()
        m_file.addAction(self.a_quit)
        m_view = self.menuBar().addMenu("&Zobrazení")
        m_view.addAction(self.a_fit)
        m_view.addAction(self.a_light)
        m_view.addAction(self.a_mslook)
        m_view.addAction(self.a_dark)
        m_acc = m_view.addMenu("Barva vzhledu")
        from PySide6.QtGui import QActionGroup
        from .theme import ACCENTS, accent_name
        self.accent_group = QActionGroup(self)
        self.a_accent = {}
        for key, (label, _h) in ACCENTS.items():
            a = QAction(label, self, checkable=True)
            a.setChecked(key == accent_name())
            a.setToolTip(f"Barva zvýraznění tlačítek a výběru: {label.lower()}")
            a.triggered.connect(lambda _c=False, k=key: self.set_accent(k))
            self.accent_group.addAction(a)
            m_acc.addAction(a)
            self.a_accent[key] = a
        m_font = m_view.addMenu("Velikost písma")
        from .theme import FONT_SCALES, font_scale_name
        self.font_group = QActionGroup(self)
        self.a_font = {}
        for key, (label, _k) in FONT_SCALES.items():
            a = QAction(label, self, checkable=True)
            a.setChecked(key == font_scale_name())
            a.setToolTip(f"Velikost písma celé aplikace: {label.lower()}")
            a.triggered.connect(lambda _c=False, k=key: self.set_font_scale(k))
            self.font_group.addAction(a)
            m_font.addAction(a)
            self.a_font[key] = a
        m_view.addAction(self.a_labels)
        m_view.addAction(self.a_heat)
        m_view.addAction(self.a_focus)
        from PySide6.QtGui import QActionGroup
        m_size = m_view.addMenu("Velikost kroužků chyb")
        grp = QActionGroup(self)
        cur = self.settings.value("zobrazeni/krouzky", "stredni")
        for key, label, r in (("male", "Malé", 9.0), ("stredni", "Střední", 13.0), ("velke", "Velké", 18.0)):
            a = QAction(label, self, checkable=True)
            a.setChecked(key == cur)
            a.triggered.connect(lambda _c=False, k=key, rr=r: self.set_marker_size(k, rr))
            grp.addAction(a)
            m_size.addAction(a)
            if key == cur:
                self.set_marker_size(key, r, save=False)
        self.a_hide_info = self._act("Skrýt informace (modré kroužky)", self._toggle_info, None,
                                     "Nezobrazovat nálezy typu info – např. volné konce na okraji kresby",
                                     checkable=True)
        m_view.addAction(self.a_hide_info)
        m_view.addAction(self.a_sketch)
        m_view.addAction(self.layers_dock.toggleViewAction())
        m_view.addAction(self.inspector_dock.toggleViewAction())
        m_view.addAction(self.sketch_dock.toggleViewAction())
        m_check = self.menuBar().addMenu("&Kontrola")
        m_check.addAction(self.a_check)
        m_check.addAction(self.a_vyber)
        m_check.addAction(self.a_prehled)
        m_check.addAction(self.a_recheck)
        m_check.addAction(self.a_ready)
        m_check.addAction(self.a_repair)
        m_check.addSeparator()
        m_check.addAction(self.a_fixguide)
        m_check.addAction(self.a_undo)
        m_check.addAction(self.a_mini)
        m_check.addAction(self.a_notify)
        m_check.addAction(self.a_timeline)
        m_check.addAction(self.a_ms_send)
        m_check.addAction(self.a_ms_help)
        m_check.addAction(self.a_predikce)
        m_check.addAction(self.a_seznam)
        m_check.addAction(self.a_spojnice)
        m_check.addAction(self.a_batch)
        m_check.addAction(self.a_compare)
        m_check.addAction(self.a_vypocet)
        m_check.addAction(self.a_teacher)
        m_check.addSeparator()
        m_check.addAction(self.a_watch)
        m_check.addAction(self.a_wip)
        m_check.addAction(self.a_region)
        m_check.addSeparator()
        m_check.addAction(self.a_settings)
        m_help = self.menuBar().addMenu("&Nápověda")
        m_help.addAction(self._act("Co aplikace umí…", self.show_features, None, "Přehled všech funkcí"))
        m_help.addAction(self._act("Průvodce…", self.show_guide, None, "Krok za krokem od zadání k odevzdání"))
        self.a_news = self._act("Co je nového…", lambda: self.show_news(force=True), None,
                                "Novinky v posledních verzích aplikace")
        m_help.addAction(self.a_news)
        m_help.addAction(self._act("Co znamenají chyby (s obrázky)…", self.show_help, "F1",
                                   "Vysvětlení jednotlivých typů chyb a pojmů"))
        m_help.addAction(self._act("Rychlé tipy – MicroStation (rovnoběžka, kolmice…)", self.show_tips, "Ctrl+T",
                                   "Jak udělat běžné konstrukce a opravy v MicroStationu"))
        m_help.addAction(self.poradce_dock.toggleViewAction())
        m_help.addAction(self._act("Klávesové zkratky", self.show_shortcuts, None,
                                   "Přehled klávesových zkratek aplikace"))
        m_help.addAction(self._act("Jak převést DGN na DXF", self._dgn_help))
        m_help.addAction(self._act("Kokeš, Atlas DMT, AutoCAD a katastr (VFK)",
                                   lambda: QMessageBox.information(self, "Jiné programy", JINE_PROGRAMY_NAVOD)))
        m_help.addSeparator()
        self.a_report = self._act("Vytvořit hlášení o problému…", self.show_report, None,
                                  "Hlášení pro vývojáře (verze, poslední kroky a chyby) – zkopírovat do chatu nebo "
                                  "uložit na plochu")
        m_help.addAction(self.a_report)
        m_help.addAction(self._act("Nahlásit chybu / složka s logy…", self._open_logs, None,
                                   "Pokud se něco pokazilo: záznam chyb je v této složce"))
        m_help.addAction(self._act("Zkontrolovat aktualizace", lambda: self.check_updates(manual=True)))
        self.a_autoupdate = self._act("Hledat aktualizace při spuštění", self._set_autoupdate, None,
                                      "Jednou denně se podívá na GitHub, jestli není novější verze. "
                                      "Zjišťuje se jen číslo verze, nic se neodesílá.", checkable=True)
        self.a_autoupdate.blockSignals(True)
        self.a_autoupdate.setChecked(self.settings.value("aktualizace/kontrolovat", True, type=bool))
        self.a_ms_send.setChecked(self.settings.value("microstation/posilat", False, type=bool))
        self.a_autoupdate.blockSignals(False)
        m_help.addAction(self.a_autoupdate)
        m_help.addAction(self._act("O aplikaci", self._about))

        self._apply_icons()
        self.a_prev.setText("Předchozí")
        self.a_next.setText("Další")
        self.a_repair.setIconText("Oprava")
        self.a_settings.setIconText("Nastavení")
        self.a_sketch.setIconText("Náčrt")
        self.a_exp_pdf.setIconText("Protokol PDF")
        self.a_open.setIconText("Otevřít")

        # ---- svislá lišta vlevo (jako mapové aplikace): stránky nahoře, akce, dole nastavení a nabídka ☰
        tb = QToolBar("Hlavní panel")
        tb.setObjectName("hlavni_panel")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setOrientation(Qt.Vertical)
        tb.setIconSize(QSize(22, 22))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        from PySide6.QtGui import QActionGroup
        self.page_group = QActionGroup(self)
        self.page_group.setExclusive(True)
        self.a_page = {}
        for key, text, tip in (("uvod", "Úvod", "Úvodní stránka – stav projektu a další krok"),
                               ("vykres", "Výkres", "Výkres a seznam chyb"),
                               ("zadani", "Zadání", "Směrnice, pokyny, náčrty, podklady"),
                               ("vypocty", "Výpočty", "Seznam souřadnic a geodetické výpočty (jako Groma)")):
            act = QAction(text, self)
            act.setCheckable(True)
            act.setToolTip(tip)
            act.triggered.connect(lambda _c=False, k=key: self.show_page(k))
            self.page_group.addAction(act)
            tb.addAction(act)
            self.a_page[key] = act
        tb.addSeparator()
        for a in (self.a_open, self.a_check, self.a_recheck, self.a_ready):
            tb.addAction(a)
        tb.addAction(self.a_exp_pdf)
        a_por = self.poradce_dock.toggleViewAction()
        self.a_poradce = a_por
        a_por.setText("Poradce")
        a_por.setShortcut(QKeySequence("Ctrl+K"))
        a_por.setToolTip("Zeptejte se na cokoli – odpověď z návodů aplikace (Ctrl+K, diktování Win+H)")
        tb.addAction(a_por)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        tb.addWidget(spacer)
        tb.addAction(self.a_settings)
        # klasická nabídka (Soubor, Zobrazení, Kontrola, Nápověda) schovaná pod ☰
        self.a_menu = QAction("Nabídka", self)
        self.a_menu.setToolTip("Všechny funkce: Soubor, Zobrazení, Kontrola, Nápověda (Alt)")
        menu_all = QMenu(self)
        for ma in self.menuBar().actions():
            if ma.menu() is not None:
                menu_all.addMenu(ma.menu())
        self.a_menu.setMenu(menu_all)
        self.a_menu.triggered.connect(lambda: self._popup_main_menu())
        tb.addAction(self.a_menu)
        self.addToolBar(Qt.LeftToolBarArea, tb)
        self.toolbar = tb
        self.menuBar().hide()
        for act in self.findChildren(QAction):  # zkratky z (schované) nabídky dál fungují
            if not act.shortcut().isEmpty():
                self.addAction(act)
        # krátké popisky pod ikonou (celé znění je v tooltipu)
        for act, short in ((self.a_open, "Otevřít"), (self.a_check, "Kontrola"), (self.a_recheck, "Znovu"),
                           (self.a_ready, "Odevzdat"), (self.a_exp_pdf, "Protokol"), (a_por, "Poradce"), (self.a_settings, "Nastavení"),
                           (self.a_menu, "Nabídka")):
            act.setIconText(short)
            btn = tb.widgetForAction(act)
            if btn is not None:
                full = act.text().replace("&", "").rstrip("…")
                btn.setToolTip(full + (f" – {act.toolTip()}" if act.toolTip() and act.toolTip() != act.text()
                                       else ""))
        for btn in tb.findChildren(QToolButton):
            btn.setMinimumWidth(66)
        # nástroje pohledu jako plovoucí lišta nad výkresem (jako ovládání mapy)
        vt = QToolBar("Pohled")
        vt.setObjectName("plovouci_lista")
        vt.setOrientation(Qt.Vertical)
        vt.setIconSize(QSize(20, 20))
        vt.setToolButtonStyle(Qt.ToolButtonIconOnly)
        a_layers = self.layers_dock.toggleViewAction()
        a_layers.setText("Vrstvy")
        a_layers.setToolTip("Panel vrstev – zapnutí a vypnutí vrstev výkresu")
        self.a_layers_panel = a_layers
        for act in (self.a_fit, self.a_labels, a_layers, self.a_heat, self.a_region, self.a_wip, self.a_sketch,
                    self.a_mini):
            vt.addAction(act)
            b = vt.widgetForAction(act)
            if b is not None:
                b.setToolTip(act.text().replace("&", "").rstrip("…") + (
                    f" – {act.toolTip()}" if act.toolTip() and act.toolTip() != act.text() else ""))
        from .canvas import _shadow
        _shadow(vt, 18, 50)
        self.view_tools = vt
        self.split.add_overlay(vt, "vlevo_nahore")
        from .prikazy import CommandSearch
        self.cmd_search = CommandSearch(self)
        _shadow(self.cmd_search, 18, 45)
        self.split.add_overlay(self.cmd_search, "nahore")
        from .minimap import Minimap
        self.minimap = Minimap(self.view)
        _shadow(self.minimap, 18, 50)
        self.split.add_overlay(self.minimap, "vlevo_dole")
        self.minimap.hide()  # ukáže se, až bude načtený výkres
        # hlavní akce je zvýrazněná (bílá ikona na modrém tlačítku)
        btn = tb.widgetForAction(self.a_check)
        if btn is not None:
            btn.setMenu(self._check_menu())
            btn.setPopupMode(QToolButton.MenuButtonPopup)
            btn.setObjectName("primarni")
            btn.setMinimumWidth(78)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        mb = tb.widgetForAction(self.a_menu)
        if mb is not None:
            mb.setPopupMode(QToolButton.InstantPopup)
        self.tabs.tabBar().hide()  # stránky přepíná lišta vlevo
        self._sync_page_buttons()
        self._apply_icons()

    def show_page(self, key: str):
        w = {"uvod": getattr(self, "home", None), "vykres": self.split, "zadani": self.zadani,
             "vypocty": getattr(self, "vypocty", None)}.get(key)
        if w is not None:
            from .crash import step
            step(f"stránka {key}")
            self.tabs.setCurrentWidget(w)

    def _sync_page_buttons(self):
        if not hasattr(self, "a_page"):
            return
        w = self.tabs.currentWidget()
        key = ("uvod" if w is getattr(self, "home", None) else "vykres" if w is self.split
               else "vypocty" if w is getattr(self, "vypocty", None) else "zadani")
        self.a_page[key].setChecked(True)

    def _popup_main_menu(self):
        btn = self.toolbar.widgetForAction(self.a_menu)
        if btn is not None and self.a_menu.menu() is not None:
            self.a_menu.menu().popup(btn.mapToGlobal(btn.rect().topRight()))

    def _apply_icons(self):
        from .theme import accent, icon, themed
        for a, name in ((self.a_open, "otevrit"), (self.a_check, "zkontrolovat"), (self.a_recheck, "znovu"),
                        (self.a_repair, "oprava"), (self.a_settings, "nastaveni"), (self.a_fit, "cele"),
                        (self.a_labels, "popisky"), (self.a_prev, "predchozi"), (self.a_next, "dalsi"),
                        (self.a_sketch, "nacrt"), (self.a_exp_pdf, "pdf"), (self.a_wip, "rozpracovany"),
                        (self.a_region, "vyrez"), (self.a_ready, "odevzdat"), (self.a_seznam, "seznam"),
                        (self.a_timeline, "casova_osa"), (self.a_print_preview, "tisk"),
                        (getattr(self, "a_poradce", None), "poradce")):
            if a is not None:
                a.setIcon(icon(name))
        for key, act in getattr(self, "a_page", {}).items():
            act.setIcon(icon(key, accent() if act.isChecked() else themed("#6B7280")))
        if getattr(self, "a_menu", None) is not None:
            self.a_menu.setIcon(icon("menu"))
        if getattr(self, "a_mini", None) is not None:
            self.a_mini.setIcon(icon("okno"))
        if getattr(self, "a_focus", None) is not None:
            self.a_focus.setIcon(icon("soustredeni"))
        if getattr(self, "a_heat", None) is not None:
            self.a_heat.setIcon(icon("teplo"))
        if getattr(self, "a_layers_panel", None) is not None:
            self.a_layers_panel.setIcon(icon("vrstvy"))
        if getattr(self, "tabs", None) is not None:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                name = "uvod" if w is getattr(self, "home", None) else "vykres" if w is self.split else \
                    "zadani" if w is self.zadani else "vypocty" if w is getattr(self, "vypocty", None) else None
                if name:
                    self.tabs.setTabIcon(i, icon(name, accent() if i == self.tabs.currentIndex()
                                                 else themed("#6B7280")))
        if getattr(self, "toolbar", None) is not None:
            self.a_check.setIcon(icon("zkontrolovat", "#FFFFFF"))  # bílá ikona na modrém tlačítku

    def set_dark(self, on: bool):
        """Tmavý režim celé aplikace (uloží se)."""
        from PySide6.QtWidgets import QApplication

        from .theme import apply_theme
        apply_theme(QApplication.instance(), bool(on))
        self._apply_icons()
        self.settings.setValue("zobrazeni/vzhled", "tmavy" if on else "svetly")
        self.issue_panel.model.layoutChanged.emit()

    def set_font_scale(self, key: str):
        """Velikost písma celé aplikace (menší / normální / větší / největší) – uloží se."""
        from PySide6.QtWidgets import QApplication

        from .theme import apply_theme, is_dark
        from .theme import set_font_scale as _set
        _set(key)
        apply_theme(QApplication.instance(), is_dark())
        self._apply_icons()
        self.settings.setValue("zobrazeni/pismo", key)
        self.issue_panel.set_card_mode(self.issue_panel.card_mode)  # výška řádků podle písma
        if key in getattr(self, "a_font", {}):
            self.a_font[key].setChecked(True)
        self.issue_panel.model.layoutChanged.emit()
        self.split._layout()

    def set_accent(self, key: str):
        """Barva vzhledu (modrá / zelená / fialová / oranžová) – uloží se."""
        from PySide6.QtWidgets import QApplication

        from .theme import apply_theme, is_dark
        from .theme import set_accent as _set
        _set(key)
        apply_theme(QApplication.instance(), is_dark())
        self._apply_icons()
        self.settings.setValue("zobrazeni/barva", key)
        if key in getattr(self, "a_accent", {}):
            self.a_accent[key].setChecked(True)
        self.issue_panel.model.layoutChanged.emit()

    def _restore_geometry(self):
        g = self.settings.value("okno/geometrie")
        if g is not None:
            self.restoreGeometry(g)
        s = self.settings.value("okno/stav2")  # (stav z dřívějšího vzhledu s lištou nahoře se nepoužije)
        if s is not None:
            self.restoreState(s)
        if getattr(self, "toolbar", None) is not None:
            self.addToolBar(Qt.LeftToolBarArea, self.toolbar)  # lišta vždy vlevo
            self.toolbar.show()
        light = self.settings.value("zobrazeni/svetle_pozadi", False, type=bool)
        self.a_light.setChecked(light)
        self.a_mslook.setChecked(self.settings.value("zobrazeni/jako_microstation", True, type=bool))
        from .theme import is_dark
        self.a_dark.blockSignals(True)
        self.a_dark.setChecked(is_dark())
        self.a_dark.blockSignals(False)

    def closeEvent(self, event):  # noqa: N802
        if getattr(self, "vypocty", None) is not None:
            self.vypocty.save()
        if getattr(self, "_mini", None) is not None:
            self._mini.close()
        if self.task is not None and self.task.is_running():
            self.task.cancel()
        self.settings.setValue("okno/geometrie", self.saveGeometry())
        self.settings.setValue("okno/stav2", self.saveState())
        self.settings.setValue("zobrazeni/svetle_pozadi", self.a_light.isChecked())
        self.settings.setValue("zobrazeni/jako_microstation", self.a_mslook.isChecked())
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

    def new_project(self):
        name, ok = QInputDialog.getText(self, "Nový projekt", "Název projektu (např. Mapování 2026 – úloha 3):")
        if not ok or not name.strip():
            return
        if self.project is not None:
            self.project.save()
        self.drawing = self.prev_drawing = None
        self.view.clear_drawing()
        self.layers.set_drawing(None)
        self.set_project(Project.new_in_default_location(name.strip()))
        self.statusBar().showMessage(f"Projekt vytvořen ve složce {self.project.root}", 10000)

    def open_project_dialog(self):
        start = self.settings.value("cesty/projekt", str(default_projects_dir()))
        path, _ = QFileDialog.getOpenFileName(
            self, "Otevřít projekt", start, "Projekt kontroly (*.kontrola projekt.yaml);;Vše (*)")
        if path:
            self.settings.setValue("cesty/projekt", str(Path(path).parent))
            self.open_project(path)

    def open_project(self, path: str):
        p = Path(path)
        try:
            if p.suffix.lower() == PROJECT_EXT:
                project = Project.import_zip(p)
                self.statusBar().showMessage(f"Projekt rozbalen do {project.root}", 10000)
            else:
                project = Project.open(p.parent if p.is_file() else p)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Projekt nelze otevřít: {exc}")
            return
        if self.project is not None:
            self.project.save()
        self.drawing = self.prev_drawing = None
        self.view.clear_drawing()
        self.layers.set_drawing(None)
        self.set_project(project)

    def save_project(self):
        if self.project is not None:
            self.project.store_issues(self.issues)
            self.project.save()
            self.statusBar().showMessage(f"Projekt uložen ({self.project.root})", 6000)

    def save_project_as(self):
        if self.project is None:
            return
        start = str(Path(self.settings.value("cesty/projekt", str(Path.home()))) / (self.project.name + PROJECT_EXT))
        path, _ = QFileDialog.getSaveFileName(self, "Uložit projekt jako", start, "Projekt kontroly (*.kontrola)")
        if not path:
            return
        self.settings.setValue("cesty/projekt", str(Path(path).parent))
        self.project.store_issues(self.issues)
        out = self.project.export_zip(path)
        self.statusBar().showMessage(f"Projekt uložen do {out}", 10000)

    # ------------------------------------------------------------------ hlídání souboru
    def _init_watch(self):
        from PySide6.QtCore import QFileSystemWatcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._file_changed)
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.timeout.connect(self._watch_fire)
        self._watch_sizes: dict[str, int] = {}
        self._watch_changed: str | None = None
        on = self.settings.value("hlidani/zapnuto", True, type=bool)
        self.a_watch.blockSignals(True)
        self.a_watch.setChecked(on)
        self.a_watch.blockSignals(False)

    def _watch_paths(self) -> list[str]:
        if self.project is None or self.drawing is None:
            return []
        src = self.project.drawing_source
        out = []
        if src and Path(src).is_file():
            out.append(str(Path(src)))
            dgn = Path(src).with_suffix(".dgn")
            if dgn.is_file():
                from ..io.dgn import find_oda_converter
                if find_oda_converter(self.project.config.oda_cesta or None):
                    out.append(str(dgn))
        return out

    def _update_watch(self):
        if not hasattr(self, "watcher"):
            return
        old = self.watcher.files()
        if old:
            self.watcher.removePaths(old)
        paths = self._watch_paths() if self.a_watch.isChecked() else []
        if paths:
            self.watcher.addPaths(paths)
        self.watch_label.setText("<span style='color:#16A34A'>●</span> hlídám " + Path(paths[0]).name
                                 if paths else "")

    def _toggle_watch(self, on: bool):
        self.settings.setValue("hlidani/zapnuto", bool(on))
        self._update_watch()
        if hasattr(self, "watcher"):
            self.statusBar().showMessage("Hlídání výkresu zapnuto – po uložení DXF se výkres sám zkontroluje."
                                         if on else "Hlídání výkresu vypnuto.", 6000)

    def _file_changed(self, path: str):
        # uložení souboru bývá víc zápisů za sebou – počkat, až se velikost přestane měnit
        self._watch_changed = path
        self._watch_sizes[path] = Path(path).stat().st_size if Path(path).exists() else -1
        self._watch_timer.start(1500)

    def _watch_fire(self):
        path = self._watch_changed
        if not path:
            return
        p = Path(path)
        size = p.stat().st_size if p.exists() else -1
        if size <= 0 or size != self._watch_sizes.get(path):
            self._watch_sizes[path] = size
            self._watch_timer.start(1500)  # ještě se zapisuje (nebo soubor chvíli neexistuje)
            return
        if self.task is not None and self.task.is_running():
            self._watch_timer.start(1500)
            return
        self._watch_changed = None
        self.statusBar().showMessage(f"{p.name} se změnil – kontroluji znovu…", 5000)
        self.recheck(p if p.suffix.lower() == ".dgn" else None, silent=True)

    def ready_check(self):
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres.")
            return
        if self.task is not None and self.task.is_running():
            return
        import copy

        from .ready_dialog import ReadyDialog, checklist_for, record_history
        cfg = copy.deepcopy(self.project.config)
        cfg.rozpracovany = False
        seznamy = self.project.attachments("seznamy")
        cfg.seznam_souradnic = str(seznamy[0].path) if seznamy else ""
        drawing, rules = self.drawing, self.project.rules
        states = self.project.issue_states()

        def job(progress, cancelled):
            return run_checks(drawing, rules, cfg, progress, cancelled)

        def done(res: CheckResult):
            if res.cancelled:
                return
            carry_states(states, res.issues, recheck=False)
            record_history(self.project, res.issues, "před odevzdáním")
            self.project.save()
            self.issue_panel.history.set_data(self.project.meta.get("historie", []))
            ReadyDialog(self.project, res.issues, checklist_for(self.project, drawing, self.project.config),
                        self).exec()

        self._run_task(job, done, "Kontrola před odevzdáním…")

    def compare_teacher(self):
        if self.drawing is None or not self.issues:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres a spusťte kontrolu (F5) – "
                                    "pak ji jde porovnat s protokolem učitele.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Protokol od učitele", "",
                                              "Protokol (*.log *.txt *.prt);;Vše (*)")
        if not path:
            return
        from ..protokol_ucitele import compare_with_teacher, read_teacher_log
        from .protokol_dialog import ProtokolDialog
        try:
            prot = read_teacher_log(path)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Protokol nelze načíst: {exc}")
            return
        if not prot.skupiny and not prot.topologie:
            QMessageBox.information(self, APP_NAME, "V souboru nejsou skupiny chyb ve formátu protokolu GISoft "
                                    "(„počet  Název vrstvy: …“). Pošlete ho prosím autorovi aplikace.")
            return
        try:
            self.project.add_attachment("dokumenty", path)
        except OSError:
            pass
        rows, summary = compare_with_teacher(prot, self.drawing, self.project.rules, self.issues)
        try:
            from ..predikce import learn
            cal = learn(rows, prot, Path(path).read_bytes().decode("cp1250", errors="ignore"))
            summary += (f" Aplikace se z protokolu učí – zatím zná {cal['protokolu']} protokolů "
                        "(Kontrola → Učitelův pohled).")
        except OSError:
            pass
        ProtokolDialog(rows, summary, prot.topologie, self).exec()

    def show_vypocet(self):
        from .vypocet_dialog import VypocetDialog
        VypocetDialog(self.project, self).exec()

    def _tab_changed(self, index: int):
        """Panel vrstev patří k výkresu – na záložce Zadání jen zabírá místo."""
        if hasattr(self, "toolbar"):
            self._sync_page_buttons()
            self._apply_icons()  # ikona vybrané záložky v barvě zvýraznění
        if not hasattr(self, "layers_dock"):
            return
        on_drawing = self.tabs.widget(index) is self.split
        docks = (self.layers_dock, getattr(self, "inspector_dock", None))
        if on_drawing:
            for d in docks:
                if d is not None and getattr(d, "_was_visible", False):
                    d.show()
        else:
            for d in docks:
                if d is not None:
                    d._was_visible = d.isVisible()
                    d.hide()

    def _toggle_wip(self, on: bool):
        if self.project is None or self._syncing_wip:
            return
        self.project.config.rozpracovany = bool(on)
        self.project.save()
        self._update_banner()
        self.statusBar().showMessage(
            "Rozpracovaný výkres: nehlásí se volné konce, neuzavřené plochy, mezery a chybějící popisy."
            if on else "Kontroluje se celý výkres jako před odevzdáním.", 8000)
        if self.drawing is not None and self.issues:
            self.run_checks()

    def _update_banner(self):
        parts = []
        if self.project is not None and self.project.config.rozpracovany:
            parts.append("<b>Rozpracovaný výkres</b> – nehlásí se volné konce, neuzavřené plochy, mezery "
                         "a chybějící popisy.")
        if self.a_region.isChecked():
            parts.append("<b>Jen výřez</b> – počítají se jen chyby v zobrazené části výkresu.")
        self.issue_panel.set_banner(" ".join(parts))

    def _toggle_region(self, on: bool):
        if on and self.drawing is None:
            self.a_region.setChecked(False)
            return
        region = self.view.visible_world_rect() if on else None
        self.issue_panel.set_region(region)
        self._update_banner()
        self.statusBar().showMessage("Počítají se jen chyby v zobrazeném výřezu." if on
                                     else "Počítají se chyby v celém výkresu.", 6000)

    def set_project(self, project: Project):
        self.project = project
        if getattr(self, "vypocty", None) is not None:
            self.vypocty.set_project(project)
        self._syncing_wip = True
        self.a_wip.setChecked(bool(project.config.rozpracovany))
        self._syncing_wip = False
        if self.a_region.isChecked():
            self.a_region.setChecked(False)
        self._update_banner()
        self.issue_panel.history.set_data(project.meta.get("historie", []))
        self.settings.setValue("projekt/posledni", str(project.root))
        self._update_title()
        self.set_issues([])
        self.zadani.set_project(project)
        self.sketch.set_project(project)
        self._apply_background(project.meta.get("podklad") or {})
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
        if suffix == PROJECT_EXT:
            self.open_project(path)
        elif suffix in (".dxf", ".dgn", ".dwg", ".vfk", ".shp", ".geojson"):
            if self.tabs.currentWidget() is self.zadani and \
                    self.zadani.tabs.currentWidget() is self.zadani.template_page:
                self.zadani.template_page.set_template(path)
            else:
                self.load_drawing_file(Path(path), add_to_project=True)
        else:
            # tabulky, náčrty a fotky patří do Zadání
            self.tabs.setCurrentWidget(self.zadani)
            self.zadani.handle_files([path])

    def load_drawing_file(self, path: Path, add_to_project: bool = True, after=None, keep_view=False):
        if self.task is not None and self.task.is_running():
            QMessageBox.information(self, APP_NAME, "Počkejte na dokončení probíhající úlohy.")
            return
        oda = self.project.config.oda_cesta if self.project else None

        def job(progress, cancelled):
            drawing = load_drawing(path, lambda p, m="": progress(int(p * 0.85), m), oda)
            progress(90, "Připravuji zobrazení…")
            return drawing, prepare_drawing(drawing)

        def done(result):
            drawing, prepared = result
            if add_to_project:
                self._remember_recent(path)
            if add_to_project and self.project is not None:
                try:
                    # u DGN si projekt pamatuje DXF, ze kterého se skutečně četlo (vedle DGN / převod)
                    real = Path(drawing.path)
                    keep = real if (real.suffix.lower() == ".dxf" and real.parent == path.parent) else path
                    self.project.set_drawing(keep)
                    self.project.save()
                except OSError as exc:
                    QMessageBox.warning(self, APP_NAME, f"Výkres se nepodařilo zkopírovat do projektu: {exc}")
            self.set_drawing(drawing, keep_view=keep_view, prepared=prepared)
            if after:
                after(drawing)

        self._run_task(job, done, f"Načítám {path.name}…", self._load_failed)

    def _remember_recent(self, path: Path):
        items = [p for p in (self.settings.value("cesty/posledni_vykresy", []) or []) if p != str(path)]
        if isinstance(items, str):
            items = [items]
        self.settings.setValue("cesty/posledni_vykresy", [str(path)] + items[:7])

    def _fill_recent(self):
        self.m_recent.clear()
        items = self.settings.value("cesty/posledni_vykresy", []) or []
        if isinstance(items, str):
            items = [items]
        items = [p for p in items if Path(p).is_file()]
        if not items:
            a = self.m_recent.addAction("(žádné)")
            a.setEnabled(False)
            return
        for p in items:
            self.m_recent.addAction(Path(p).name, lambda _checked=False, p=p: self.open_path(p)).setToolTip(p)

    def _load_failed(self, msg: str):
        title = "Výkres nelze otevřít"
        QMessageBox.warning(self, title, msg)

    def set_drawing(self, drawing: Drawing, keep_view: bool = False, prepared=None):
        if getattr(self, "home", None) is not None and self.tabs.currentWidget() is self.home:
            self.tabs.setCurrentWidget(self.split)
        if self.drawing is not None and self.drawing is not drawing:
            self.prev_drawing = self.drawing  # pro „Porovnat verze výkresu“
        if getattr(self, "_compare_dlg", None) is not None:
            self._compare_dlg.close()
        self.drawing = drawing
        tr, center = self.view.transform(), self.view.mapToScene(self.view.viewport().rect().center())
        self.view.set_drawing(drawing, prepared)
        if keep_view:
            self.view.setTransform(tr)
            self.view.centerOn(center)
        elif self.a_region.isChecked():
            self.a_region.setChecked(False)  # jiný výkres – výřez už neplatí
        self.layers.set_drawing(drawing)
        self.set_issues([])
        self._update_watch()
        n = len(drawing.features)
        self.info_label.setText(f"Načteno {n} prvků, {sum(1 for l in drawing.layers.values() if l.count)} vrstev.")
        self._update_title()
        if drawing.warnings:
            self.statusBar().showMessage(f"Upozornění při načítání: {len(drawing.warnings)} "
                                         f"(např. {drawing.warnings[0]})", 15000)

    # ------------------------------------------------------------------ kontroly
    def run_checks(self, after=None):
        if self.task is not None and self.task.is_running():
            # výkres se ještě načítá / probíhá jiná úloha – kontrola se spustí hned po ní
            self._queued_check = after if callable(after) else True
            self.info_label.setText("Kontrola se spustí po dokončení probíhající úlohy…")
            return
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres (tlačítko Otevřít výkres "
                                                    "nebo přetažením souboru do okna).")
            return
        drawing, rules, config = self.drawing, self.project.rules, self.project.config
        seznamy = self.project.attachments("seznamy")
        config.seznam_souradnic = str(seznamy[0].path) if seznamy else ""

        def job(progress, cancelled):
            return run_checks(drawing, rules, config, progress, cancelled)

        self._run_task(job, lambda res: self._checks_done(res, after), "Spouštím kontroly…")

    def _checks_done(self, res: CheckResult, after=None):
        if res.cancelled:
            self.info_label.setText("Kontrola byla zrušena.")
            return
        carry_states(self.project.issue_states(), res.issues, recheck=callable(after))
        self._mark_new(res.issues)
        from .. import tahak
        tahak.record(self.settings, str(self.project.root), res.issues)
        from .ready_dialog import record_history
        record_history(self.project, res.issues)
        self.issue_panel.history.set_data(self.project.meta.get("historie", []))
        summary = None
        if callable(after):
            summary = after(res)
        self._checked_once = True
        self.set_issues(res.issues, summary)
        self.project.store_issues(res.issues)
        self._snapshot(res.issues)
        self._send_to_ms(res.issues)
        self.project.save()
        if res.notes:
            self.statusBar().showMessage(" | ".join(res.notes[:4]), 20000)
        self.last_notes = res.notes

    def recheck(self, path: Path | None = None, silent: bool = False):
        if self.project is None:
            return
        path = path or self.project.drawing_path_for_loading()
        if path is None:
            self.run_checks()
            return
        old = list(self.issues)

        def compare_text(res: CheckResult) -> str:
            cmp = compare(old, res.issues)
            msg = (f"Opakovaná kontrola: {len(res.issues)} problémů (předtím {len(old)}). {cmp.text()}")
            if silent:
                self.statusBar().showMessage("Výkres se změnil – " + msg, 15000)
                todo = sum(1 for i in res.issues if i.state == "nová" and i.severity.value != "info")
                self.notify("Výkres zkontrolován po uložení",
                            f"Opraveno {cmp.fixed}, nové {cmp.new}, zbývá opravit {todo}.")
            else:
                QMessageBox.information(self, "Zkontrolovat znovu", msg)
            return msg

        self.project.refresh_drawing_copy()
        self.load_drawing_file(path, add_to_project=False, keep_view=True,
                               after=lambda d: self.run_checks(after=compare_text))

    def _mark_new(self, issues: list[Issue]):
        """Označí chyby, které přibyly od minulé kontroly téhož výkresu (★ nová)."""
        from collections import Counter
        # (výkres se může načíst z kopie v projektu i z původního místa – porovná se název souboru)
        cur = Path(self.drawing.source_path or self.drawing.path).name.lower() if self.drawing is not None else None
        prev_name, prev_keys = getattr(self, "_last_check", (None, None))
        if prev_keys is not None and prev_name == cur:
            left = Counter(prev_keys)
            for iss in issues:
                if left[iss.key] > 0:
                    left[iss.key] -= 1
                else:
                    iss.nove = True
        self._last_check = (cur, [i.key for i in issues])

    def set_issues(self, issues: list[Issue], summary: str | None = None):
        self.issues = issues
        self.view.set_issues(issues)
        self.issue_panel.set_issues(issues, summary or "")
        self.split.set_issue_count(sum(1 for i in issues if i.state == "nová" and i.severity.value != "info"))
        if not issues and not summary:
            self._checked_once = False
        elif issues and summary:
            self._checked_once = True  # obnovený výsledek poslední kontroly
        self.refresh_home()

    def refresh_home(self):
        if getattr(self, "home", None) is not None:
            self.home.refresh()
            from ..skore import compute_score
            if getattr(self, "_checked_once", False) and self.drawing is not None:
                sk = compute_score(self.issues, bool(self.project and self.project.rules.pravidla))
                self.issue_panel.set_score(sk)
            else:
                self.issue_panel.set_score(None)

    def repair(self):
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres.")
            return
        if self.task is not None and self.task.is_running():
            return
        if Path(self.drawing.path).suffix.lower() != ".dxf":
            QMessageBox.information(self, APP_NAME, "Automatická oprava umí upravit jen výkres DXF. Tento výkres "
                                                    f"({Path(self.drawing.path).suffix}) opravte ve svém programu – "
                                                    "pomůže Opravný průvodce (Ctrl+G).")
            return
        from ..repair import repair_drawing
        from .repair_dialog import RepairDialog
        src = self.drawing.source_path or self.drawing.path
        dlg = RepairDialog(src, self.project.config.tolerance, bool(self.project.rules.pravidla), self)
        if not dlg.exec():
            return
        out, opts = dlg.out_path(), dlg.options()
        drawing, rules, config = self.drawing, self.project.rules, self.project.config

        def job(progress, cancelled):
            progress(10, "Opravuji výkres…")
            return repair_drawing(drawing, rules, config, out, opts)

        def done(rep):
            text = rep.text() + f"\n\nOpravený výkres: {out}"
            if rep.skipped:
                text += "\n\nNeopraveno:\n" + "\n".join("• " + s for s in rep.skipped[:12])
                if len(rep.skipped) > 12:
                    text += f"\n… a dalších {len(rep.skipped) - 12}"
            if QMessageBox.question(self, "Automatická oprava", text + "\n\nOtevřít opravený výkres "
                                    "a zkontrolovat ho?") == QMessageBox.Yes:
                self.load_drawing_file(Path(out), add_to_project=True, after=lambda d: self.run_checks())

        self._run_task(job, done, "Opravuji výkres…")

    def edit_settings(self):
        dlg = SettingsDialog(self.project.config, self.project.rules, self)
        if dlg.exec():
            self.project.config = dlg.result_config()
            dlg.apply_rules_settings(self.project.rules)
            self.project.save()
            self._update_banner()

    def _rules_changed(self):
        self.refresh_home()
        self.statusBar().showMessage(f"Pravidla: {len(self.project.rules.pravidla)}. Pro jejich použití "
                                     f"spusťte kontrolu (F5).", 8000)

    def _project_modified(self):
        self.refresh_home()
        self.sketch.refresh()
        self._update_title()

    def _sketch_note_changed(self, rel: str, text: str):
        self.project.save()
        self.zadani.images_page.browser.sync_note(rel, text)

    def show_sketch_beside(self):
        self.sketch.refresh()
        if not self.sketch.images():
            QMessageBox.information(self, APP_NAME, "V projektu zatím nejsou žádné náčrty ani fotky. "
                                                    "Přidejte je na záložce Zadání → Náčrt a fotky.")
            self.tabs.setCurrentWidget(self.zadani)
            self.zadani.tabs.setCurrentWidget(self.zadani.images_page)
            return
        self.tabs.setCurrentWidget(self.split)
        was_hidden = not self.sketch_dock.isVisible()
        self.sketch_dock.show()
        self.sketch_dock.raise_()
        if was_hidden and not self.sketch_dock.isFloating():
            self.resizeDocks([self.sketch_dock], [max(320, self.width() // 4)], Qt.Horizontal)

    def start_georef(self, rel: str):
        """Umístění podkladu (náčrt, PDF vzor) pod výkres podle 2 bodů."""
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete kontrolovaný výkres.")
            return
        path = self.project.root / rel
        pm = load_pixmap(path)
        if pm.isNull():
            QMessageBox.warning(self, APP_NAME, f"Obrázek {path.name} nelze načíst.")
            return
        from .georef_dialog import GeorefDialog
        if getattr(self, "_georef", None) is not None:
            self._georef.close()
        old = self.project.meta.get("podklad") or {}
        dlg = GeorefDialog(pm, self.view, float(old.get("pruhlednost", 0.5)), self)

        def done(params: dict):
            bg = {"zapnuto": True, "obrazek": rel, **params}
            self.project.meta["podklad"] = bg
            self.project.save()
            self._apply_background(bg)
            self.zadani.images_page.refresh()
            self.statusBar().showMessage(f"Podklad umístěn: měřítko {params['meritko']:.4f} m/px, "
                                         f"natočení {params['rotace']:.2f}°", 10000)

        dlg.finished_params.connect(done)
        self.tabs.setCurrentWidget(self.split)
        dlg.show()
        self._georef = dlg

    def _apply_background(self, bg: dict):
        if not bg or not bg.get("zapnuto") or not bg.get("obrazek") or self.project is None:
            self.view.set_background_image(None)
            return
        path = self.project.root / bg["obrazek"]
        if not path.is_file():
            self.view.set_background_image(None)
            return
        self.view.set_background_image(load_pixmap(path), float(bg.get("x", 0)), float(bg.get("y", 0)),
                                       float(bg.get("meritko", 0.1)), float(bg.get("rotace", 0)),
                                       float(bg.get("pruhlednost", 0.5)))

    def verify_list(self):
        from .seznam_dialog import SeznamDialog
        path = ""
        if self.project is not None:
            s = self.project.attachments("seznamy")
            path = str(s[0].path) if s else ""
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres – seznam se porovná s jeho body.")
            return
        dlg = SeznamDialog(self, path)
        self._seznam_dlg = dlg
        dlg.show()

    def _snapshot(self, issues):
        """Snímek výkresu do časové osy (jen když se od minula změnil)."""
        if self.drawing is None or getattr(self, "_region", None):
            return
        try:
            from ..casova_osa import snapshot
            from ..checks.base import Severity
            from ..skore import compute_score
            open_ = [i for i in issues if i.state == "nová"]
            snapshot(self.project, self.drawing.path, {
                "prvku": len(self.drawing.features),
                "chyby": sum(1 for i in open_ if i.severity == Severity.CHYBA),
                "varovani": sum(1 for i in open_ if i.severity == Severity.VAROVANI),
                "skore": compute_score(issues, bool(self.project.rules.pravidla)).hodnota})
        except Exception:  # noqa: BLE001 – časová osa nesmí zastavit kontrolu
            import logging
            logging.getLogger(__name__).exception("Snímek časové osy se nepodařilo uložit")

    def _toggle_ms_send(self, on: bool):
        self.settings.setValue("microstation/posilat", bool(on))
        if on and self.drawing is not None and self.issues:
            self._send_to_ms(self.issues)

    def _send_to_ms(self, issues):
        if not self.a_ms_send.isChecked() or self.drawing is None:
            return
        try:
            from ..microstation import write_errors
            out = write_errors(self.drawing.source_path or self.drawing.path, issues)
            self.statusBar().showMessage(f"Chyby pro MicroStation: {out.name} (v MicroStationu F6 / vba run KV_Nacist)",
                                         6000)
        except OSError as exc:
            self.statusBar().showMessage(f"Seznam chyb pro MicroStation nejde uložit: {exc}", 8000)

    def show_ms_link(self):
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout

        from ..microstation import NAVOD, install_macro
        dlg = QDialog(self)
        dlg.setWindowTitle("Propojení s MicroStationem")
        dlg.resize(720, 620)
        lay = QVBoxLayout(dlg)
        tb = QTextBrowser()
        tb.setHtml(NAVOD)
        lay.addWidget(tb, 1)
        row = QHBoxLayout()
        b = QPushButton("Uložit makro KontrolaVykresu.bas…")
        b.setProperty("primarni", True)

        def save():
            d = QFileDialog.getExistingDirectory(dlg, "Kam uložit makro", str(Path.home()))
            if d:
                out = install_macro(d)
                QMessageBox.information(dlg, "Makro", f"Makro uloženo: {out}\n\nTeď ho importujte ve VBA editoru "
                                        "MicroStationu (postup v okně).")
        b.clicked.connect(save)
        on = QPushButton("Zapnout posílání chyb")
        on.clicked.connect(lambda: (self.a_ms_send.setChecked(True), self._toggle_ms_send(True)))
        row.addWidget(b)
        row.addWidget(on)
        row.addStretch(1)
        close = QPushButton("Zavřít")
        close.clicked.connect(dlg.accept)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec()

    def show_prediction(self):
        from .predikce_dialog import PredikceDialog
        if self.drawing is None or not getattr(self, "_checked_once", False):
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres a zkontrolujte ho (F5).")
            return
        PredikceDialog(self).exec()

    def _check_menu(self) -> QMenu:
        m = QMenu(self)
        m.aboutToShow.connect(lambda: self._fill_check_menu(m))
        m.setToolTipsVisible(True)
        self._fill_check_menu(m)
        return m

    def _fill_check_menu(self, m: QMenu):
        from .vyber_kontrol import PRESETY, vlastni_sady
        m.clear()
        m.addAction(self.a_vyber)
        m.addSeparator()
        for name, tip, _p in PRESETY:
            a = m.addAction(f"Zkontrolovat: {name}")
            a.setToolTip(tip)
            a.triggered.connect(lambda _c=False, n=name: self.run_preset(n))
        sady = vlastni_sady(self.settings)
        if sady:
            m.addSeparator()
            for name, ids in sady.items():
                a = m.addAction(f"Moje sada: {name}")
                a.setToolTip(f"{len(ids)} kontrol")
                a.triggered.connect(lambda _c=False, n=name: self.run_preset(n))

    def run_preset(self, name: str):
        from .vyber_kontrol import apply_preset_to
        apply_preset_to(self.project.config, name, self.settings)
        self.project.save()
        self.statusBar().showMessage(f"Sada kontrol: {name}", 5000)
        if self.drawing is not None:
            self.a_check.trigger()

    def show_overview(self):
        from .prehled_dialog import PrehledDialog
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres.")
            return
        self._prehled_dlg = PrehledDialog(self)
        self._prehled_dlg.show()

    def show_check_selection(self):
        from .vyber_kontrol import VyberKontrol
        dlg = VyberKontrol(self)
        if dlg.exec() and dlg.run_now and self.drawing is not None:
            self.a_check.trigger()

    def notify(self, title: str, text: str):
        """Upozornění Windows vpravo dole – jen když je aplikace v pozadí (pracuje se v MicroStationu)."""
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
        if not self.settings.value("upozorneni/zapnuto", True, type=bool):
            return
        if QApplication.activeWindow() is not None and not getattr(self, "_notify_always", False):
            return  # okno je vpředu – stačí stavový řádek
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if getattr(self, "_tray", None) is None:
            self._tray = QSystemTrayIcon(self.windowIcon(), self)
            self._tray.setToolTip("Kontrola výkresu")
            self._tray.messageClicked.connect(lambda: (self.showNormal(), self.raise_(), self.activateWindow()))
            self._tray.activated.connect(lambda _r: (self.showNormal(), self.raise_(), self.activateWindow()))
        self._tray.show()
        self._tray.showMessage(title, text, QSystemTrayIcon.Information, 8000)
        self._last_notify = (title, text)

    def _set_notify(self, on: bool):
        self.settings.setValue("upozorneni/zapnuto", bool(on))

    def set_focus_mode(self, on: bool):
        """Schová vše kromě výkresu; dole karta s vybranou chybou (Opraveno / Další), Esc ukončí."""
        from PySide6.QtGui import QShortcut
        from .soustredeni import FocusBar
        if getattr(self, "_focus_bar", None) is None:
            self._focus_bar = FocusBar(self)
            self.split.add_overlay(self._focus_bar, "dole")
            self._focus_esc = QShortcut(QKeySequence("Esc"), self, activated=lambda: self.a_focus.setChecked(False))
            self.issue_panel.issueSelected.connect(lambda _n: self._focus_bar.refresh() if self.split.focus_mode
                                                   else None)
        bar = self._focus_bar
        if on:
            if self.split.focus_mode:
                return
            self.show_page("vykres")
            docks = [d for d in self.findChildren(QDockWidget) if d.isVisible()]
            self._focus_saved = {"panel": self.split.panel_visible, "status": self.statusBar().isVisible(),
                                 "toolbar": self.toolbar.isVisible(),
                                 "docks": docks,
                                 "over": [w for w, _ in self.split.overlays if w.isVisible() and w is not bar]}
            self.split.focus_mode = True
            self.toolbar.hide()
            self.statusBar().hide()
            for d in docks:
                d.hide()
            for w in self._focus_saved["over"]:
                w.hide()
            self.minimap.suppressed = True
            self.split.set_panel_visible(False, animate=False)
            self._focus_esc.setEnabled(True)
            bar.show()
            if self.issue_panel.current_issue() is None or self.issue_panel.current_issue().state != "nová":
                self.issue_panel.next_open()
            bar.refresh()
            self.split._layout()
            iss = self.issue_panel.current_issue()
            if iss is not None:
                self.view.highlight_issue(iss.number, zoom=True)
        else:
            if not self.split.focus_mode:
                return
            sv = getattr(self, "_focus_saved", {})
            self.split.focus_mode = False
            self._focus_esc.setEnabled(False)
            bar.hide()
            self.toolbar.setVisible(sv.get("toolbar", True))
            self.statusBar().setVisible(sv.get("status", True))
            for d in sv.get("docks", []):
                d.show()
            for w in sv.get("over", []):
                w.show()
            self.minimap.suppressed = False
            self.split.set_panel_visible(sv.get("panel", True), animate=False)
            self.split._layout()

    def show_mini(self):
        from .mini_okno import MiniOkno
        if getattr(self, "_mini", None) is None:
            self._mini = MiniOkno(self)
        if not self.issue_panel.current_issue() and self.issues:
            self.issue_panel.step(1)
        self._mini.refresh()
        self._mini.show()
        self._mini.raise_()

    def show_timeline(self):
        from .timeline_dialog import TimelineDialog
        TimelineDialog(self).exec()

    def print_preview(self, path: str | None = None, meritko: int | None = None):
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres.")
            return
        if meritko is None:
            default = (self.project.rules.meritko if self.project is not None else None) or 500
            meritko, ok = QInputDialog.getInt(self, "Náhled tisku", "Měřítko 1:", int(default), 50, 100000, 50)
            if not ok:
                return
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Náhled tisku", str(Path(self.drawing.path).with_name(
                Path(self.drawing.path).stem + f"_tisk_1-{meritko}.pdf")), "PDF (*.pdf)")
            if not path:
                return
        w, h = self.view.render_print_pdf(path, meritko, Path(self.drawing.path).name)
        self.statusBar().showMessage(f"Náhled tisku 1:{meritko} uložen ({w:.0f} × {h:.0f} mm): {path}", 8000)
        return path

    def show_fix_guide(self):
        from .pruvodce_opravou import PruvodceOpravou
        if self.drawing is None or not self.issues:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres a zkontrolujte ho (F5).")
            return
        dlg = PruvodceOpravou(self)
        self._fix_dlg = dlg
        dlg.show()

    def verify_lines(self):
        from .spojnice_dialog import SpojniceDialog
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres.")
            return
        s = self.project.attachments("seznamy") if self.project is not None else []
        dlg = SpojniceDialog(self, str(s[0].path) if s else "")
        self._spojnice_dlg = dlg
        dlg.show()

    def batch_check(self):
        start = self.settings.value("cesty/vykres", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, "Výkresy ke kontrole", start,
                                                DRAWING_FILTER)
        if not files:
            return
        from .batch_dialog import BatchDialog
        BatchDialog(self, files).exec()

    def compare_versions(self):
        if self.drawing is None:
            QMessageBox.information(self, APP_NAME, "Nejdřív otevřete výkres.")
            return
        prev = getattr(self, "prev_drawing", None)
        if prev is None:
            self.compare_with_file()
            return
        self._show_compare(prev)

    def compare_with_file(self):
        start = self.settings.value("cesty/vykres", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, "Starší verze výkresu k porovnání", start, DRAWING_FILTER)
        if not path:
            return
        if self.task is not None and self.task.is_running():
            QMessageBox.information(self, APP_NAME, "Počkejte na dokončení probíhající úlohy.")
            return
        oda = self.project.config.oda_cesta if self.project else None
        self._run_task(lambda progress, cancelled: load_drawing(Path(path), lambda p, m="": progress(int(p), m), oda),
                       self._show_compare, f"Načítám {Path(path).name}…", self._load_failed)

    def _show_compare(self, old: Drawing):
        from ..porovnani import compare
        from .compare_dialog import CompareDialog
        if getattr(self, "_compare_dlg", None) is not None:
            self._compare_dlg.close()
        changes = compare(old, self.drawing)
        name = lambda d: Path(d.source_path or d.path).name  # noqa: E731
        dlg = CompareDialog(self.view, changes, name(old), name(self.drawing), self)
        dlg.otherRequested.connect(self.compare_with_file)
        dlg.finished.connect(lambda *_: setattr(self, "_compare_dlg", None))
        self._compare_dlg = dlg
        dlg.show()
        self.tabs.setCurrentWidget(self.split)
        self.statusBar().showMessage(f"Porovnání verzí: {len(changes)} změn.", 8000)

    def _set_autoupdate(self, on: bool):
        self.settings.setValue("aktualizace/kontrolovat", bool(on))

    def _illustrations(self, check_ids) -> dict[str, bytes]:
        """Obrázky „chyba / správně“ (PNG) pro tisk – stejné jako ve vysvětlení „?“."""
        from PySide6.QtCore import QBuffer, QIODevice

        from .help_topics import illustration
        out: dict[str, bytes] = {}
        for cid in check_ids:
            try:
                pm = illustration(cid, 520)
            except Exception:  # noqa: BLE001 – obrázek je jen pomůcka
                pm = None
            if pm is None:
                continue
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            pm.save(buf, "PNG")
            out[cid] = bytes(buf.data())
        return out

    def maybe_show_news(self):
        """Po aktualizaci jednou ukáže, co je nového (při prvním spuštění vůbec ne – tam je průvodce)."""
        from .. import novinky
        if novinky.unseen(self.settings):
            self.show_news()
        else:
            novinky.mark_seen(self.settings)

    def show_news(self, force: bool = False):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

        from .. import novinky
        items = novinky.NOVINKY if force else novinky.unseen(self.settings)
        if not items:
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle("Co je nového")
        dlg.resize(620, 520)
        lay = QVBoxLayout(dlg)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setHtml("<h2 style='margin:0'>Co je nového</h2>" + novinky.html(items)
                   + "<p style='color:gray'>Všechny funkce najdete v Nápověda → Co aplikace umí, "
                     "nebo je vyhledejte polem nahoře (Ctrl+F).</p>")
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.button(QDialogButtonBox.Ok).setText("Rozumím")
        bb.button(QDialogButtonBox.Ok).setMinimumWidth(110)
        bb.accepted.connect(dlg.accept)
        lay.addWidget(bb)
        novinky.mark_seen(self.settings)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        self._news_dlg = dlg
        return dlg

    def maybe_check_updates(self):
        """Při spuštění: nejvýš jednou denně, jen u sestaveného .exe a když to uživatel nevypnul."""
        import time

        from ..aktualizace import BUILD
        if BUILD is None or not self.settings.value("aktualizace/kontrolovat", True, type=bool):
            return
        last = float(self.settings.value("aktualizace/posledni", 0) or 0)
        if time.time() - last < 86400:
            return
        self.check_updates(manual=False)

    def check_updates(self, manual: bool = False):
        import threading
        import time

        from ..aktualizace import fetch_latest
        self.settings.setValue("aktualizace/posledni", time.time())

        def work():
            try:
                latest = fetch_latest()
                err = ""
            except Exception as exc:  # noqa: BLE001 – bez internetu apod.
                latest, err = None, str(exc)
            try:
                self._updateResult.emit(latest, err, manual)
            except RuntimeError:
                pass  # okno se mezitím zavřelo – výsledek už nikoho nezajímá

        threading.Thread(target=work, daemon=True).start()
        if manual:
            self.statusBar().showMessage("Zjišťuji, jestli je novější verze…", 5000)

    def _on_update_result(self, latest, err: str, manual: bool):
        from ..aktualizace import BUILD, DOWNLOAD_URL, RELEASES_URL, is_newer, version_text
        if is_newer(latest):
            self.statusBar().showMessage(f"K dispozici je novější verze (sestavení č. {latest}).", 20000)
            box = QMessageBox(self)
            box.setWindowTitle("Nová verze")
            box.setTextFormat(Qt.RichText)
            box.setText(f"Je k dispozici novější verze programu (sestavení č. {latest}, vy máte č. {BUILD}).<br><br>"
                        f"<a href='{DOWNLOAD_URL}'>Stáhnout KontrolaVykresu.exe</a> "
                        f"(<a href='{RELEASES_URL}'>co je nového</a>)<br><br>"
                        "Stažený soubor stačí spustit místo starého; projekty a nastavení zůstanou.")
            box.setTextInteractionFlags(Qt.TextBrowserInteraction)
            import sys
            b_now = None
            if getattr(sys, "frozen", False) and sys.platform == "win32":
                b_now = box.addButton("Aktualizovat teď", QMessageBox.AcceptRole)
                box.addButton("Později", QMessageBox.RejectRole)
            box.exec()
            if b_now is not None and box.clickedButton() is b_now:
                self.update_now()
        elif manual:
            if err:
                QMessageBox.information(self, "Aktualizace", f"Nepodařilo se spojit s GitHubem ({err}).")
            elif BUILD is None:
                QMessageBox.information(self, "Aktualizace", "Program běží ze zdrojových kódů – aktualizujte "
                                        f"přes git. Poslední zveřejněné sestavení: č. {latest or '?'}.")
            else:
                QMessageBox.information(self, "Aktualizace", f"Máte nejnovější verzi ({version_text()}).")

    def update_now(self):
        """Stáhne novou verzi, nahradí .exe a program spustí znovu (projekty a nastavení zůstanou)."""
        import tempfile
        from pathlib import Path

        from PySide6.QtWidgets import QApplication, QProgressDialog

        from ..aktualizace import download, install_and_restart
        dlg = QProgressDialog("Stahuji novou verzi…", "Zrušit", 0, 100, self)
        dlg.setWindowTitle("Aktualizace")
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dest = Path(tempfile.gettempdir()) / "KontrolaVykresu_nova.exe"
        cancelled = {"v": False}
        dlg.canceled.connect(lambda: cancelled.update(v=True))

        def prog(done, total):
            if total:
                dlg.setValue(int(done * 100 / total))
            QApplication.processEvents()
            if cancelled["v"]:
                raise OSError("zrušeno")
        try:
            download(dest, prog)
        except Exception as exc:  # noqa: BLE001
            dlg.close()
            if not cancelled["v"]:
                QMessageBox.warning(self, "Aktualizace", f"Novou verzi se nepodařilo stáhnout ({exc}).")
            return
        dlg.close()
        if self.project is not None:
            self.project.save()
        install_and_restart(dest)
        self.close()
        QApplication.instance().quit()

    def undo_dispatch(self):
        if self.tabs.currentWidget() is getattr(self, "vypocty", None):
            self.vypocty.undo()
        else:
            self.issue_panel.undo()

    def redo_dispatch(self):
        if self.tabs.currentWidget() is getattr(self, "vypocty", None):
            self.vypocty.redo()

    def show_report(self, problem: str = ""):
        from .crash import show_report_dialog
        self._report_dlg = show_report_dialog(self, problem)
        return self._report_dlg

    def offer_crash_report(self):
        """Minule se aplikace nečekaně ukončila – nabídnout hlášení."""
        if QMessageBox.question(
                self, "Aplikace se minule nečekaně ukončila",
                "Minule se aplikace nezavřela řádně (spadla nebo zamrzla).\n\nChcete vytvořit hlášení o problému? "
                "Stačí ho zkopírovat a poslat – pomůže to chybu opravit.") == QMessageBox.Yes:
            self.show_report("Minule se aplikace nečekaně ukončila.")

    def _open_logs(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from .crash import ISSUES_URL, log_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))
        if QMessageBox.question(self, "Nahlásit chybu", "Otevřela se složka se záznamem chyb (chyby.log).\n\n"
                                "Chcete otevřít stránku pro nahlášení chyby na GitHubu? (Soubor chyby.log "
                                "tam můžete přiložit.)") == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(ISSUES_URL))

    def set_marker_size(self, key: str, radius: float, save: bool = True):
        from .drawing_view import IssueMarker
        IssueMarker.RADIUS = radius
        self.view.refresh_markers()
        self.view.request_declutter()
        self.view.viewport().update()
        if save:
            self.settings.setValue("zobrazeni/krouzky", key)

    def _toggle_info(self, hide: bool):
        from ..checks.base import Severity as _S
        self.issue_panel.sev_boxes[_S.INFO].setChecked(not hide)

    def show_shortcuts(self):
        """Přehled zkratek sestavený z akcí okna (vždy odpovídá skutečnosti)."""
        rows = []
        for a in self.findChildren(QAction):
            sc = a.shortcut().toString(QKeySequence.NativeText)
            if sc and a.text():
                rows.append((a.text().replace("&", "").rstrip("…"), sc))
        rows += [("Předchozí / další chyba", "F7 / F8"), ("Opraveno", "Ctrl+Enter"), ("Ignorovat", "Ctrl+Delete"),
                 ("Přiblížení", "kolečko myši"), ("Posun výkresu", "tažení prostředním / pravým tlačítkem")]
        seen, html = set(), []
        for t, sc in sorted(rows, key=lambda r: r[0].lower()):
            if (t, sc) in seen:
                continue
            seen.add((t, sc))
            html.append(f"<tr><td style='padding:3px 16px 3px 0'>{t}</td><td><b>{sc}</b></td></tr>")
        QMessageBox.information(self, "Klávesové zkratky", "<table>" + "".join(html) + "</table>")

    def show_features(self):
        from .features_dialog import FeaturesDialog
        FeaturesDialog(self).exec()

    def show_tips(self):
        from .tips import TipsDialog
        TipsDialog(self).exec()

    def show_guide(self):
        from .guide_dialog import GuideDialog
        GuideDialog(self).exec()

    def show_help(self):
        iss = self.issue_panel.current_issue()
        self.issue_panel.explain(iss.check_id if iss else "_zavaznost")

    def _dgn_help(self):
        QMessageBox.information(self, "Převod DGN na DXF", DGN_NAVOD)

    def _about(self):
        from ..aktualizace import version_text
        QMessageBox.about(self, APP_NAME,
                          f"<h3>{APP_NAME}</h3>Verze {version_text()}<br><br>"
                          "Předkontrola topologie a atributů geodetických výkresů (DXF z MicroStationu) "
                          "před odevzdáním.<br><br>Všechna data zůstávají na tomto počítači, nic se "
                          "nikam neodesílá.<br><br>Knihovny: PySide6 (Qt), ezdxf, shapely, openpyxl, "
                          "pdfplumber, reportlab.")

    # ------------------------------------------------------------------ export
    def export(self, kind: str):
        if not self.issues:
            QMessageBox.information(self, "Export", "Není co exportovat – nejdřív spusťte kontrolu (F5).")
            return
        from ..export import dxf_export, tables
        base = Path(self.drawing.source_path or self.drawing.path).stem if self.drawing else "vykres"
        start_dir = Path(self.settings.value("cesty/export", str(Path.home())))
        spec = {
            "csv": ("Uložit seznam chyb", f"{base}_chyby.csv", "CSV (*.csv)"),
            "xlsx": ("Uložit seznam chyb", f"{base}_chyby.xlsx", "Excel (*.xlsx)"),
            "pdf": ("Uložit protokol", f"{base}_protokol.pdf", "PDF (*.pdf)"),
            "todo": ("Uložit seznam k opravě", f"{base}_k_oprave.pdf", "PDF (*.pdf)"),
            "html": ("Uložit interaktivní protokol", f"{base}_protokol.html", "HTML (*.html)"),
            "dxf": ("Uložit DXF s chybami", f"{base}_kontrola.dxf", "DXF (*.dxf)"),
            "log": ("Uložit protokol (.log)", f"{base}.log", "Protokol (*.log *.txt)"),
        }[kind]
        path, _ = QFileDialog.getSaveFileName(self, spec[0], str(start_dir / spec[1]), spec[2])
        if not path:
            return
        self.settings.setValue("cesty/export", str(Path(path).parent))
        visible = self.issue_panel.visible_numbers()
        issues = [i for i in self.issues if i.number in visible]
        if len(issues) != len(self.issues):
            ans = QMessageBox.question(self, "Export", f"Filtr zobrazuje {len(issues)} z {len(self.issues)} "
                                       "chyb. Exportovat jen zobrazené?\n\n(Ne = exportovat všechny)",
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ans == QMessageBox.Cancel:
                return
            if ans == QMessageBox.No:
                issues = list(self.issues)
        try:
            if kind == "csv":
                tables.export_csv(issues, path)
            elif kind == "xlsx":
                tables.export_xlsx(issues, path, drawing_name=base + ".dxf")
            elif kind == "dxf":
                if self.drawing is None:
                    raise ValueError("Není otevřený výkres.")
                dxf_export.export_dxf(self.drawing, issues, path)
            elif kind == "pdf":
                self._export_pdf(issues, path)
            elif kind == "html":
                self._export_html(issues, path)
            elif kind == "todo":
                from ..export.pdf_report import export_checklist
                todo = [i for i in issues if i.state == "nová" and i.severity != Severity.INFO]
                name = Path(self.drawing.source_path or self.drawing.path).name if self.drawing else ""
                export_checklist(issues, path, name, self._issue_images(todo, 80, 300),
                                 self._illustrations({i.check_id for i in todo}))
            elif kind == "log":
                from ..export.mgeo_log import export_mgeo_log
                if self.drawing is None:
                    raise ValueError("Není otevřený výkres.")
                export_mgeo_log(self.drawing, self.project.rules, issues, path, self.project.name,
                                tolerance=self.project.config.tolerance)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"Export se nezdařil: {exc}")
            return
        self.statusBar().showMessage(f"Uloženo: {path}", 10000)
        if QMessageBox.question(self, "Export", f"Uloženo do\n{path}\n\nOtevřít soubor?") == QMessageBox.Yes:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @staticmethod
    def _png(pm) -> bytes:
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        pm.save(buf, "PNG")
        return bytes(buf.data())

    def _issue_images(self, issues: list[Issue], limit: int = 60, size: int = 420) -> dict[int, bytes]:
        """Výřezy výkresu kolem chyb (pro PDF)."""
        images: dict[int, bytes] = {}
        if self.drawing is None:
            return images
        self.view.set_print_mode(True)
        try:
            for iss in [i for i in issues if i.state == "nová"][:limit]:
                span = 20.0
                if iss.geometry is not None and not iss.geometry.is_empty:
                    b = iss.geometry.bounds
                    span = min(80.0, max(span, (b[2] - b[0]) * 1.3, (b[3] - b[1]) * 1.3))
                images[iss.number] = self._png(self.view.render_region(iss.x, iss.y, span, size))
        finally:
            self.view.set_print_mode(False)
        return images

    def _export_html(self, issues: list[Issue], path: str):
        from ..export.html_report import export_html
        overview, pos, size = None, {}, None
        if self.drawing is not None:
            self.view.set_print_mode(True)
            try:
                pm, pos = self.view.render_overview_positions(issues, 1100, markers=False)
                overview, size = self._png(pm), (pm.width(), pm.height())
            finally:
                self.view.set_print_mode(False)
        images = self._issue_images(issues, 80, 300)
        name = Path(self.drawing.source_path or self.drawing.path).name if self.drawing else ""
        export_html(issues, path, name, self.project.name if self.project else "", overview, pos, size, images,
                    bool(self.project and self.project.rules.pravidla), rozsah=self.scope_text())

    def _export_pdf(self, issues: list[Issue], path: str):
        from ..export.pdf_report import export_pdf
        limit = 60
        images = self._issue_images(issues, limit)
        overview = None
        if self.drawing is not None:
            self.view.set_print_mode(True)
            try:
                overview = self._png(self.view.render_overview(issues, 900))
            finally:
                self.view.set_print_mode(False)
        drawing_name = Path(self.drawing.source_path or self.drawing.path).name if self.drawing else ""
        export_pdf(issues, path, drawing_name=drawing_name, project_name=self.project.name,
                   rules_count=len(self.project.rules.pravidla), images=images, overview=overview,
                   notes=getattr(self, "last_notes", []), tolerance=self.project.config.tolerance,
                   image_limit=limit, rozsah=self.scope_text())

    def scope_text(self) -> str:
        """Rozsah kontroly do protokolu – jen když neproběhly všechny kontroly."""
        from ..checks.base import REGISTRY
        cfg = self.project.config
        off = [cls.nazev for cid, cls in REGISTRY.items() if not cfg.settings(cid).zapnuto]
        if not off:
            return ""
        shown = ", ".join(off[:12]) + (f" a dalších {len(off) - 12}" if len(off) > 12 else "")
        return f"Provedeno {len(REGISTRY) - len(off)} z {len(REGISTRY)} kontrol. Nespuštěno: {shown}."

    def _feature_info(self, iss: Issue) -> str:
        """Popis prvku, ke kterému chyba patří – aby šel ve výkresu najít."""
        if self.drawing is None or not iss.feature_ids:
            return ""
        if getattr(self, "_by_id_of", None) is not self.drawing:
            self._by_id, self._by_id_of = self.drawing.by_id(), self.drawing
        f = self._by_id.get(iss.feature_ids[0])
        if f is None:
            return ""
        from html import escape

        from ..checks.attributes import _what
        parts = [f"{_what(f)} na vrstvě <b>{escape(f.layer)}</b>"]
        if f.text:
            parts.append(f"text „{escape(f.text[:60])}“")
        if f.block_name:
            parts.append(f"buňka {escape(f.block_name)}")
        if self.project is not None:
            parts.append(f"barva {escape(self.project.rules.describe_feature_color(f))}")
        if f.geom_type.value in ("linie", "polygon"):
            parts.append(f"styl {escape(f.linetype)}")
        if len(iss.feature_ids) > 1:
            parts.append(f"(a dalších {len(iss.feature_ids) - 1} prvků)")
        text = ", ".join(parts)
        li = self.drawing.layers.get(f.layer)
        if li is not None and (li.off or li.frozen):
            text += (" – <span style='color:#B45309'><b>vrstva je ve výkresu vypnutá</b>, proto prvek v MicroStationu "
                     "nevidíte. Zapněte ji ve Správci vrstev (Level Manager / Zobrazení vrstev).</span>")
        elif f.geom_type.value in ("bod",) and f.dxftype == "POINT":
            text += " – bod je ve výkresu jen malá tečka, přibližte si ho."
        return text

    def _on_issue_selected(self, number: int):
        self.view.highlight_issue(number, zoom=not getattr(self, "_no_zoom", False))

    def _on_feature_clicked(self, fid: int):
        if self.drawing is None or getattr(self.view, "_pick_mode", False):
            return
        f = self.drawing.by_id().get(fid) if fid >= 0 else None
        self.view.highlight_feature(fid)
        from ..rules import RuleSet
        self.inspector.show_feature(f, self.drawing, self.project.rules if self.project else RuleSet(), self.issues)
        if f is not None:
            self.inspector_dock.show()
            self.inspector_dock.raise_()
            mine = [i for i in self.issues if fid in i.feature_ids]
            if mine:
                self._no_zoom = True
                try:
                    self.issue_panel.select_issue(mine[0].number)
                finally:
                    self._no_zoom = False
                self.view.highlight_feature(fid)

    def _on_marker_clicked(self, number: int):
        self.issue_panel.select_issue(number)
        self.view.highlight_issue(number, zoom=False)

    def _on_states_changed(self):
        self.view.refresh_markers()
        self.view.refresh_heatmap()  # opravené chyby z tepelné mapy zmizí
        self.split.set_issue_count(sum(1 for i in self.issues if i.state == "nová" and i.severity.value != "info"))
        if self.split.focus_mode and getattr(self, "_focus_bar", None) is not None:
            self._focus_bar.refresh()
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
            self._run_queued_check()

        def fail(msg):
            self.progress.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.task = None
            self.info_label.setText("")
            (on_fail or (lambda m: QMessageBox.warning(self, APP_NAME, m)))(msg)
            self._run_queued_check()

        self.task.progress.connect(prog)
        self.task.finished.connect(fin)
        self.task.failed.connect(fail)
        self.task.start()

    def _run_queued_check(self):
        q = getattr(self, "_queued_check", None)
        if q is None or (self.task is not None and self.task.is_running()):
            return
        self._queued_check = None
        QTimer.singleShot(0, lambda: self.run_checks(q if callable(q) else None))

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
