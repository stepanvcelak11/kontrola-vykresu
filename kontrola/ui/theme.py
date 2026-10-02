"""Vzhled aplikace: světlé téma (styl Qt) a jednoduché čárové ikony."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap

ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#E8F0FE"
BG = "#F4F6FA"
PANEL = "#FFFFFF"
BORDER = "#E3E7EE"
BORDER_STRONG = "#CBD2DC"
HOVER = "#F1F4F9"
SUBTLE = "#F8FAFC"
TEXT = "#111827"
MUTED = "#6B7280"

# čárové ikony 24×24 (styl „outline“), barva se doplní při vykreslení
_ICONS = {
    "otevrit": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1"/><path d="M3 7v11a2 2 0 0 0 2 2h13l3-8H7l-3 8"/>',
    "zkontrolovat": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
    "znovu": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    "oprava": '<path d="M14.7 6.3a4 4 0 0 0 5 5L12 19a2.1 2.1 0 0 1-3-3l7.7-7.7z"/><path d="M5 5l3 3"/>'
              '<path d="M3 8l2-2 3 3-2 2z"/>',
    "nastaveni": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/>'
                 '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "cele": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "popisky": '<path d="M3 12V4h8l10 10-8 8L3 12z"/><circle cx="7.5" cy="8" r="1.3"/>',
    "predchozi": '<path d="M15 5l-7 7 7 7"/>',
    "dalsi": '<path d="M9 5l7 7-7 7"/>',
    "nacrt": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/>'
             '<path d="M21 16l-5-5-9 9"/>',
    "rozpracovany": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/><path d="M14 20h6" stroke-dasharray="2 2"/>',
    "vyrez": '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M2 6h14a2 2 0 0 1 2 2v14"/>',
    "odevzdat": '<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>',
    "poradce": '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "sk_topologie": '<circle cx="5" cy="18" r="2.2"/><circle cx="12" cy="6" r="2.2"/><circle cx="19" cy="18" r="2.2"/>'
                    '<path d="M6.2 16l4.7-8M13.1 8l4.7 8M7.2 18h9.6"/>',
    "sk_atributy": '<path d="M3 12V4h8l10 10-8 8L3 12z"/><circle cx="7.5" cy="8" r="1.4"/>',
    "sk_kartografie": '<path d="M5 19L12 4l7 15"/><path d="M8 13h8"/>',
    "sk_geometrie": '<path d="M3 17l5-9 6 6 7-10"/><circle cx="8" cy="8" r="1.6"/><circle cx="14" cy="14" r="1.6"/>',
    "vrstvy": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "teplo": '<path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.4 1.3-3.9 2.4-5 .2 1.6 1 2.6 2.1 3 .6-2.6-.5-5.2.5-8z"/>',
    "soustredeni": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/><circle cx="12" cy="12" r="2.5"/>',
    "okno": '<rect x="3" y="7" width="13" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-3"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "hledat": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4.2-4.2"/>',
    "uvod": '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    "vykres": '<path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z"/><path d="M9 4v14M15 6v14"/>',
    "cad": '<path d="M4 20l7-16 9 16"/><path d="M7.5 13h9"/><circle cx="11" cy="4" r="1.6"/>',
    "vypocty": '<rect x="5" y="3" width="14" height="18" rx="2"/><rect x="8" y="6" width="8" height="3.5" rx="0.6"/>'
               '<path d="M8.5 13h.01M12 13h.01M15.5 13h.01M8.5 16.5h.01M12 16.5h.01M15.5 16.5h.01"/>',
    "zadani": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="M8.5 10h7M8.5 13.5h7M8.5 17h4"/>',
    "tisk": '<path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/>',
    "casova_osa": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "seznam": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.2"/><circle cx="4.5" cy="12" r="1.2"/>'
              '<circle cx="4.5" cy="18" r="1.2"/>',
    "pdf": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>'
           '<path d="M8 13h8M8 17h5"/>',
}


# tmavý režim: každá barva světlého vzhledu má svůj tmavý protějšek (nahrazuje se najednou, bez řetězení)
DARK_MAP = {  # vzhled „Studio“: břidlicově modrá tma, panely o odstín světlejší (návrh vzhledu A)
    "#F3F4F6": "#0E141B", "#FFFFFF": "#111821", "#D1D5DB": "#2A3644", "#1F2937": "#E6EDF3",
    "#6B7280": "#8B98A5", "#9CA3AF": "#6B7785", "#2563EB": "#3B82F6", "#1D4ED8": "#2563EB",
    "#DBEAFE": "#12304A", "#EEF2F7": "#1A232E", "#93C5FD": "#3B82F6", "#F9FAFB": "#0F151C",
    "#E5E7EB": "#1E2833", "#EEF0F3": "#1A232E", "#374151": "#C9D1D9", "#EFF6FF": "#102233",
    "#BFDBFE": "#264866", "#1E3A8A": "#BFDBFE", "#FEF3C7": "#3A2A0C", "#FCD34D": "#806521",
    "#78350F": "#FDE68A", "#DC2626": "#F87171", "#B45309": "#FBBF24", "#4B5563": "#A9B4BF", "#C0C4CC": "#4A5664",
    "#F4F6FA": "#0B1016", "#E3E7EE": "#1E2833", "#CBD2DC": "#2A3644", "#F1F4F9": "#16202A",
    "#F8FAFC": "#0F151C", "#111827": "#E6EDF3", "#E8F0FE": "#123040", "#EEF2FF": "#16233A",
    "#C7D2FE": "#2E4A6A", "#0F172A": "#05080C", "#1E40AE": "#BFDBFE",
}
_dark = False

# barva vzhledu (zvýraznění): modrá je výchozí, ostatní vzniknou otočením odstínu modrých tónů stylu
ACCENTS = {"tyrkysova": ("Tyrkysová (Studio)", 172), "modra": ("Modrá", None), "zelena": ("Zelená", 158),
           "fialova": ("Fialová", 262), "oranzova": ("Oranžová", 24)}
VYCHOZI_ACCENT = "tyrkysova"
_ACCENT_JAS = {"tyrkysova": 0.66}  # tyrkysová je v plném jasu na bílý text moc světlá
_accent = VYCHOZI_ACCENT


# velikost písma celé aplikace (pro menší displeje / horší zrak)
FONT_SCALES = {"mensi": ("Menší", 0.9), "normalni": ("Normální", 1.0), "vetsi": ("Větší", 1.15),
               "nejvetsi": ("Největší", 1.3)}
_font_scale = "normalni"
_base_font: QFont | None = None


def set_font_scale(name: str) -> None:
    global _font_scale
    _font_scale = name if name in FONT_SCALES else "normalni"


def font_scale_name() -> str:
    return _font_scale


def _scale_pt(css: str) -> str:
    k = FONT_SCALES[_font_scale][1]
    if k == 1.0:
        return css
    import re
    return re.sub(r"(\d+(?:\.\d+)?)pt\b", lambda m: f"{float(m.group(1)) * k:.2f}pt", css)


def set_accent(name: str) -> None:
    global _accent
    _accent = name if name in ACCENTS else VYCHOZI_ACCENT


def accent_name() -> str:
    return _accent


def _accent_color(hexcol: str) -> str:
    """Modrý tón převedený na zvolenou barvu vzhledu (jas a sytost zůstanou)."""
    hue = ACCENTS[_accent][1]
    if hue is None:
        return hexcol
    c = QColor(hexcol)
    h, sat, light, _a = c.getHslF()
    # jen výrazné modré tóny zvýraznění – modrošedé texty a pozadí vzhledu Studio zůstanou
    if h < 0 or sat < 0.5 or not (190 / 360 <= h <= 245 / 360):
        return hexcol
    jas = _ACCENT_JAS.get(_accent, 1.0) if 0.25 <= light <= 0.75 else 1.0
    out = QColor.fromHslF(hue / 360, sat, min(1.0, light * jas))
    return out.name().upper()


def _to_accent(css: str) -> str:
    if ACCENTS[_accent][1] is None:
        return css
    import re
    return re.sub(r"#[0-9A-Fa-f]{6}\b", lambda m: _accent_color(m.group(0)), css)


def accent(color: str = ACCENT) -> str:
    """Barva zvýraznění v aktuálním vzhledu (tmavý režim i zvolená barva)."""
    return _accent_color(themed(color))


def is_dark() -> bool:
    return _dark


def themed(color: str) -> str:
    """Barva ze světlého vzhledu převedená na aktuální vzhled."""
    return DARK_MAP.get(color.upper(), color) if _dark else color


def _to_dark(css: str) -> str:
    import re
    return re.sub(r"#[0-9A-Fa-f]{6}\b", lambda m: DARK_MAP.get(m.group(0).upper(), m.group(0)), css)


def icon(name: str, color: str | None = None, size: int = 40) -> QIcon:
    """Ikona z vestavěné sady (vykreslená z SVG, ostrá i na displejích s vyšším rozlišením)."""
    color = color or themed(TEXT)
    body = _ICONS.get(name)
    if body is None:
        return QIcon()
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:  # bez QtSvg aplikace funguje dál, jen bez ikon
        return QIcon()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    ic = QIcon()
    for mode, col in ((QIcon.Normal, color), (QIcon.Disabled, themed("#9CA3AF"))):
        r = renderer if col == color else QSvgRenderer(QByteArray(svg.replace(color, col).encode("utf-8")))
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p, QRectF(0, 0, size, size))
        p.end()
        ic.addPixmap(pm, mode)
    return ic


STYLESHEET = f"""
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}
QToolTip {{ background: #0F172A; color: white; border: none; padding: 6px 9px; border-radius: 6px; }}

QMenuBar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; padding: 3px 6px; }}
QMenuBar::item {{ padding: 5px 11px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {HOVER}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER_STRONG}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 26px 6px 24px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::item:disabled {{ color: #9CA3AF; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}

QToolBar {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDER}; padding: 6px 10px; spacing: 4px; }}
QToolBar::separator {{ width: 1px; background: {BORDER}; margin: 7px 8px; }}
QToolButton {{ padding: 6px 10px; border: 1px solid transparent; border-radius: 8px; color: #374151; }}
QToolButton:hover {{ background: {HOVER}; border-color: {BORDER}; color: {TEXT}; }}
QToolButton:pressed {{ background: #E5E7EB; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; border-color: #C7D2FE; color: {ACCENT_HOVER}; }}
QToolButton#primarni {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3B82F6, stop:1 {ACCENT});
    color: white; font-weight: 700; padding: 6px 16px; border: 1px solid {ACCENT_HOVER}; }}
QToolButton#primarni:hover {{ background: {ACCENT_HOVER}; }}

QPushButton {{ background: {PANEL}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 6px 14px;
    min-height: 18px; }}
QPushButton:hover {{ background: {HOVER}; border-color: #9CA3AF; }}
QPushButton:pressed {{ background: #E5E7EB; }}
QPushButton:disabled {{ color: #9CA3AF; background: {SUBTLE}; border-color: {BORDER}; }}
QPushButton:flat {{ border: none; background: transparent; }}
QDialog QPushButton:default {{ background: {ACCENT}; color: white; border-color: {ACCENT}; font-weight: 600; }}
QDialog QPushButton:default:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[primarni="true"] {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3B82F6, stop:1 {ACCENT});
    color: white; border-color: {ACCENT_HOVER}; font-weight: 700; }}
QPushButton[primarni="true"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[primarni="true"]:disabled {{ background: #93C5FD; border-color: #93C5FD; color: white; }}
QPushButton[uspech="true"] {{ background: #16A34A; color: white; border-color: #15803D; font-weight: 700; }}
QPushButton[uspech="true"]:hover {{ background: #15803D; }}
QPushButton#rychly_filtr {{ padding: 4px 13px; border-radius: 14px; border-color: {BORDER}; color: #374151; }}
QPushButton#rychly_filtr:hover {{ border-color: {BORDER_STRONG}; }}
QPushButton#rychly_filtr:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; font-weight: 700; }}
QPushButton#nastroj {{ text-align: left; padding: 9px 12px; border-radius: 10px; border-color: {BORDER};
    background: {SUBTLE}; font-weight: 600; }}
QPushButton#nastroj:hover {{ background: {ACCENT_SOFT}; border-color: #C7D2FE; color: {ACCENT_HOVER}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QTextBrowser {{
    background: {PANEL}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 5px 8px;
    selection-background-color: {ACCENT}; selection-color: white; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: #9CA3AF; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT}; }}
QTextBrowser {{ padding: 8px 10px; }}

QTabWidget::pane {{ border: none; background: {BG}; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; margin: 4px 2px 4px 0; border: 1px solid transparent;
    border-radius: 8px; color: {MUTED}; font-weight: 600; }}
QTabBar::tab:selected {{ color: {ACCENT_HOVER}; background: {ACCENT_SOFT}; border-color: #C7D2FE; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; background: {HOVER}; }}
QTabWidget#hlavni_zalozky > QTabBar {{ background: {PANEL}; }}
QTabWidget#hlavni_zalozky > QTabBar::tab {{ padding: 8px 18px; margin: 6px 4px 6px 0; font-size: 10.5pt; }}

QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; margin-top: 26px;
    padding: 14px 12px 12px 12px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 8px; top: 4px;
    padding: 0 4px; color: #374151; }}

QTableView, QTreeView, QListWidget, QListView {{ background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 10px; alternate-background-color: {SUBTLE}; gridline-color: {BORDER};
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; outline: 0; }}
QTableView::item {{ padding: 3px 6px; border: none; }}
QTableView::item:hover, QListWidget::item:hover, QTreeView::item:hover {{ background: {HOVER}; }}
QTableView::item:selected, QListWidget::item:selected, QTreeView::item:selected {{
    background: {ACCENT_SOFT}; color: {TEXT}; }}
QListWidget::item {{ padding: 5px 6px; border-radius: 6px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {SUBTLE}; border: none; border-bottom: 1px solid {BORDER};
    padding: 7px 8px; font-weight: 700; color: #4B5563; }}
QTableCornerButton::section {{ background: {SUBTLE}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #CBD2DC; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #9CA3AF; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #CBD2DC; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: #9CA3AF; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 8px 10px; border-bottom: 1px solid {BORDER};
    font-weight: 700; color: #374151; }}
QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:hover {{ background: #C7D2FE; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QSplitter::handle:vertical {{ height: 6px; }}
QMainWindow::separator {{ background: {BG}; width: 6px; height: 6px; }}
QMainWindow::separator:hover {{ background: #C7D2FE; }}

QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; color: #374151; }}
QStatusBar QLabel {{ color: #374151; padding: 0 8px; }}
QProgressBar {{ border: none; border-radius: 6px; background: #E5E7EB; height: 12px; text-align: center;
    font-size: 8pt; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #60A5FA, stop:1 {ACCENT});
    border-radius: 6px; }}
QCheckBox {{ spacing: 7px; }}
QSlider::groove:horizontal {{ height: 6px; background: #E5E7EB; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {PANEL}; border: 2px solid {ACCENT}; width: 14px; margin: -5px 0;
    border-radius: 8px; }}

QScrollArea#navod_oblast, QWidget#navod_obsah {{ background: transparent; }}
QLabel#krok_nadpis {{ font-size: 11.5pt; font-weight: 800; }}
QLabel#uvod_nadpis {{ font-size: 21pt; font-weight: 800; }}
QLabel#uvod_podnadpis {{ color: {MUTED}; font-size: 10pt; }}
QLabel#karta_cislo {{ font-size: 18pt; font-weight: 800; }}
QLabel#karta_popis {{ color: {MUTED}; font-size: 9pt; }}
QLabel#sekce {{ color: {MUTED}; font-size: 8.5pt; font-weight: 800; letter-spacing: 0.6px; }}
QLabel#navod {{ background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 8px 10px;
    color: #1E3A8A; }}
QLabel#banner {{ background: #FEF3C7; border: 1px solid #FCD34D; border-radius: 10px; padding: 7px 10px;
    color: #78350F; }}
QFrame#karta {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#karta:hover {{ border-color: {BORDER_STRONG}; }}
QFrame#hero {{ border: none; border-radius: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E40AF, stop:0.55 #2563EB, stop:1 #0EA5E9); }}
QFrame#hero QLabel {{ color: white; background: transparent; }}
QFrame#hero QLabel#uvod_podnadpis {{ color: #E0ECFF; }}
QLabel#souhrn {{ color: #374151; }}
QScrollArea#cad_paleta QToolButton {{ padding: 2px; margin: 0; border-radius: 6px; }}
QScrollArea#cad_paleta, QScrollArea#cad_paleta > QWidget > QWidget {{ background: {PANEL}; }}
QLabel#cad_paleta_nadpis {{ color: {MUTED}; font-size: 8pt; font-weight: 600; padding: 6px 2px 1px 2px; }}
QLabel#cad_vyzva {{ font-weight: 600; color: {ACCENT}; }}
QLabel#cad_titulek {{ font-weight: 600; }}
QToolBar#hlavni_panel {{ background: {PANEL}; border: none; border-right: 1px solid {BORDER}; padding: 6px 4px;
    spacing: 2px; }}
QToolBar#hlavni_panel QToolButton {{ padding: 5px 2px; margin: 1px 4px; border-radius: 10px; font-size: 8.5pt; }}
QToolBar#hlavni_panel QToolButton:checked {{ background: {ACCENT_SOFT}; color: #1E40AE; border: 1px solid #C7D2FE;
    font-weight: 700; }}
QTableView#karty_chyb {{ background: transparent; border: none; }}
QTableView#karty_chyb::item, QTableView#karty_chyb::item:hover, QTableView#karty_chyb::item:selected {{
    background: transparent; border: none; }}
QToolBar#hlavni_panel QToolButton#primarni {{ min-width: 66px; padding-right: 12px; }}
QToolButton#primarni::menu-button {{ border: none; background: transparent; width: 12px;
    border-top-right-radius: 10px; border-bottom-right-radius: 10px; }}
QToolButton#primarni::menu-button:hover {{ background: rgba(255, 255, 255, 40); }}
QToolButton#primarni::menu-arrow {{ image: url("{{SIPKA_BILA}}"); width: 8px; height: 8px; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolBar#plovouci_lista {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; padding: 4px;
    spacing: 2px; }}
QToolBar#plovouci_lista QToolButton {{ padding: 6px; border-radius: 8px; }}
QLineEdit#hledat_prikaz {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 19px;
    padding: 8px 16px; font-size: 10pt; min-height: 22px; }}
QLineEdit#hledat_prikaz:focus {{ border: 1.5px solid {ACCENT}; }}
QFrame#minimapa {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#plovouci_panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 16px; }}
QPushButton#plovouci_tlacitko {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px;
    font-weight: 700; color: #374151; padding: 0 6px; }}
QPushButton#plovouci_tlacitko:hover {{ background: {ACCENT_SOFT}; color: {ACCENT_HOVER}; border-color: #C7D2FE; }}
"""


def _arrow_files() -> dict[str, str]:
    """Šipky pro rozbalovací seznamy a číselná pole (stylesheet potřebuje soubory obrázků)."""
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPen, QPolygonF
    d = Path(tempfile.gettempdir()) / "kontrola_vykresu_ui"
    d.mkdir(exist_ok=True)
    out = {}
    for name, pts in (("dolu", [(2, 5), (8, 11), (14, 5)]), ("nahoru", [(2, 11), (8, 5), (14, 11)])):
        for state, col in (("", themed("#4B5563")), ("_off", themed("#C0C4CC")), ("_bila", "#FFFFFF")):
            f = d / f"sipka_{name}{state}{'_tmava' if _dark else ''}.png"
            if not f.exists():
                pm = QPixmap(32, 32)
                pm.fill(Qt.transparent)
                p = QPainter(pm)
                p.setRenderHint(QPainter.Antialiasing)
                p.setPen(QPen(QColor(col), 3.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline(QPolygonF([QPointF(x * 2, y * 2) for x, y in pts]))
                p.end()
                pm.save(str(f))
            out[name + state] = f.as_posix()
    return out


def _arrow_css(a: dict[str, str]) -> str:
    return f"""
QComboBox {{ padding-right: 22px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 20px;
    border: none; }}
QComboBox::down-arrow {{ image: url("{a['dolu']}"); width: 10px; height: 10px; }}
QComboBox::down-arrow:disabled {{ image: url("{a['dolu_off']}"); }}
QComboBox QAbstractItemView {{ border: 1px solid {BORDER}; background: {PANEL}; selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT}; outline: 0; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 18px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
    width: 18px; border: none; border-left: 1px solid #E5E7EB; border-top-right-radius: 6px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
    width: 18px; border: none; border-left: 1px solid #E5E7EB; border-bottom-right-radius: 6px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover {{ background: #F3F4F6; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{a['nahoru']}"); width: 8px; height: 8px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{a['dolu']}"); width: 8px; height: 8px; }}
QCheckBox::indicator, QGroupBox::indicator {{ width: 15px; height: 15px; }}
"""


def fit_headers(table, extra: int = 30) -> None:
    """Sloupce tabulky aspoň tak široké, aby se vešel nadpis (neořezávat „Tloušťka“ na „oušťka“)."""
    hh = table.horizontalHeader()
    fm = hh.fontMetrics()
    f = hh.font()
    f.setBold(True)
    from PySide6.QtGui import QFontMetrics
    fm = QFontMetrics(f)
    model = table.model()
    for c in range(model.columnCount()):
        text = str(model.headerData(c, Qt.Horizontal) or "")
        need = fm.horizontalAdvance(text) + extra
        if table.columnWidth(c) < need:
            table.setColumnWidth(c, need)


BEZPECNE_PISMO = False  # bezpečný start: výchozí písmo systému (bez Segoe UI Variable)


def apply_theme(app, dark: bool = False) -> None:
    """Nastaví styl Fusion se světlou (nebo tmavou) paletou a vlastním stylesheetem."""
    global _dark
    _dark = dark
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(themed(BG)))
    pal.setColor(QPalette.Base, QColor(themed(PANEL)))
    pal.setColor(QPalette.AlternateBase, QColor(themed("#F9FAFB")))
    pal.setColor(QPalette.Text, QColor(themed(TEXT)))
    pal.setColor(QPalette.WindowText, QColor(themed(TEXT)))
    pal.setColor(QPalette.Button, QColor(themed(PANEL)))
    pal.setColor(QPalette.ButtonText, QColor(themed(TEXT)))
    pal.setColor(QPalette.Highlight, QColor(accent()))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipBase, QColor(themed("#111827")))
    pal.setColor(QPalette.ToolTipText, QColor("white"))
    pal.setColor(QPalette.PlaceholderText, QColor(themed("#9CA3AF")))
    pal.setColor(QPalette.Mid, QColor(themed(MUTED)))
    app.setPalette(pal)
    global _base_font
    if _base_font is not None:
        f = QFont(_base_font)
    else:
        f = app.font()
    if _base_font is None and not BEZPECNE_PISMO and (f.family() in ("", "Sans Serif", "MS Shell Dlg 2")
                                                       or f.pointSizeF() < 9.5):
        import sys
        if sys.platform == "win32":
            from PySide6.QtGui import QFontDatabase
            fams = set(QFontDatabase.families())
            # Windows 11: modernější Segoe UI Variable, jinak klasické Segoe UI
            f = QFont("Segoe UI Variable Text" if "Segoe UI Variable Text" in fams else "Segoe UI")
        f.setPointSizeF(9.75)
    if _base_font is None:
        _base_font = QFont(f)
    f.setPointSizeF(_base_font.pointSizeF() * FONT_SCALES[_font_scale][1])
    app.setFont(f)
    try:
        files = _arrow_files()
        css = (STYLESHEET + _arrow_css(files)).replace("{SIPKA_BILA}", files["dolu_bila"])
    except OSError:  # bez zápisu do dočasné složky zůstanou výchozí šipky
        css = STYLESHEET.replace('image: url("{SIPKA_BILA}");', "")
    app.setStyleSheet(_scale_pt(_to_accent(_to_dark(css) if dark else css)))
