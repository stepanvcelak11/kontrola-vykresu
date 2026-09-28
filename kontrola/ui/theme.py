"""Vzhled aplikace: světlé téma (styl Qt) a jednoduché čárové ikony."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap

ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#DBEAFE"
BG = "#F3F4F6"
PANEL = "#FFFFFF"
BORDER = "#D1D5DB"
TEXT = "#1F2937"
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
    "pdf": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>'
           '<path d="M8 13h8M8 17h5"/>',
}


def icon(name: str, color: str = TEXT, size: int = 40) -> QIcon:
    """Ikona z vestavěné sady (vykreslená z SVG, ostrá i na displejích s vyšším rozlišením)."""
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
    for mode, col in ((QIcon.Normal, color), (QIcon.Disabled, "#9CA3AF")):
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
QToolTip {{ background: #111827; color: white; border: none; padding: 5px 8px; border-radius: 4px; }}

QMenuBar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {ACCENT_SOFT}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

QToolBar {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDER}; padding: 4px 6px; spacing: 2px; }}
QToolBar::separator {{ width: 1px; background: {BORDER}; margin: 6px 6px; }}
QToolButton {{ padding: 5px 8px; border: 1px solid transparent; border-radius: 6px; }}
QToolButton:hover {{ background: #EEF2F7; border-color: {BORDER}; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; border-color: #93C5FD; }}
QToolButton#primarni {{ background: {ACCENT}; color: white; font-weight: 600; padding: 5px 14px; }}
QToolButton#primarni:hover {{ background: {ACCENT_HOVER}; }}

QPushButton {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 12px; }}
QPushButton:hover {{ background: #F9FAFB; border-color: #9CA3AF; }}
QPushButton:pressed {{ background: #E5E7EB; }}
QPushButton:disabled {{ color: #9CA3AF; background: #F3F4F6; }}
QPushButton[primarni="true"] {{ background: {ACCENT}; color: white; border-color: {ACCENT}; font-weight: 600; }}
QPushButton[primarni="true"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[uspech="true"] {{ background: #16A34A; color: white; border-color: #16A34A; font-weight: 600; }}
QPushButton[uspech="true"]:hover {{ background: #15803D; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QTextBrowser {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 6px;
    selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}

QTabWidget::pane {{ border: none; background: {BG}; }}
QTabBar::tab {{ background: transparent; padding: 8px 18px; margin-right: 2px; border: none;
    border-bottom: 2px solid transparent; color: {MUTED}; font-weight: 600; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom-color: {ACCENT}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px;
    padding: 10px 8px 8px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {MUTED}; }}

QTableView, QTreeView, QListWidget, QListView {{ background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 6px; alternate-background-color: #F9FAFB; gridline-color: #EEF0F3;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; outline: 0; }}
QTableView::item {{ padding: 2px 4px; }}
QHeaderView::section {{ background: #F9FAFB; border: none; border-bottom: 1px solid {BORDER};
    border-right: 1px solid #EEF0F3; padding: 5px 6px; font-weight: 600; color: #374151; }}

QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 6px 8px; border-bottom: 1px solid {BORDER};
    font-weight: 600; }}
QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QSplitter::handle:vertical {{ height: 6px; }}

QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: #374151; padding: 0 6px; }}
QProgressBar {{ border: 1px solid {BORDER}; border-radius: 5px; background: #F3F4F6; height: 14px;
    text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

QLabel#karta_cislo {{ font-size: 20px; font-weight: 700; }}
QLabel#karta_popis {{ color: {MUTED}; font-size: 11px; }}
QLabel#banner {{ background: #FEF3C7; border: 1px solid #FCD34D; border-radius: 6px; padding: 5px 8px;
    color: #78350F; }}
QFrame#karta {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel#souhrn {{ color: #374151; }}
"""


def apply_theme(app) -> None:
    """Nastaví styl Fusion se světlou paletou a vlastním stylesheetem."""
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.Base, QColor(PANEL))
    pal.setColor(QPalette.AlternateBase, QColor("#F9FAFB"))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(PANEL))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipBase, QColor("#111827"))
    pal.setColor(QPalette.ToolTipText, QColor("white"))
    pal.setColor(QPalette.PlaceholderText, QColor("#9CA3AF"))
    pal.setColor(QPalette.Mid, QColor(MUTED))
    app.setPalette(pal)
    f = app.font()
    if f.family() in ("", "Sans Serif", "MS Shell Dlg 2") or f.pointSizeF() < 9.5:
        import sys
        if sys.platform == "win32":
            f = QFont("Segoe UI")
        f.setPointSizeF(9.75)
    app.setFont(f)
    app.setStyleSheet(STYLESHEET)
