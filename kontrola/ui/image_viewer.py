"""Prohlížeč náčrtů a fotek: zoom, posun, otáčení, přepínání, poznámky."""

from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
                               QListView, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                               QSpinBox, QSplitter, QVBoxLayout, QWidget)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".pdf"}

_cache: dict[tuple[str, int, float], QPixmap] = {}


def pdf_page_count(path: str | Path) -> int:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    except Exception:
        return 1


def load_pixmap(path: str | Path, page: int = 0) -> QPixmap:
    """Načte obrázek (JPG/PNG/…) nebo stránku PDF jako QPixmap."""
    path = Path(path)
    key = (str(path), page, path.stat().st_mtime if path.exists() else 0)
    if key in _cache:
        return _cache[key]
    pm = QPixmap()
    if path.suffix.lower() == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pg = pdf.pages[min(page, len(pdf.pages) - 1)]
                img = pg.to_image(resolution=130).original
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                pm.loadFromData(buf.getvalue(), "PNG")
        except Exception:
            pm = QPixmap()
    else:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)  # otočení fotek podle EXIF
        img = reader.read()
        if not img.isNull():
            pm = QPixmap.fromImage(img)
    if len(_cache) > 40:
        _cache.clear()
    _cache[key] = pm
    return pm


class ImageView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(Qt.darkGray)
        self.item: QGraphicsPixmapItem | None = None
        self.rotation = 0

    def set_pixmap(self, pm: QPixmap | None):
        self.scene().clear()
        self.item = None
        self.rotation = 0
        self._user_zoom = False
        self.resetTransform()
        if pm is None or pm.isNull():
            return
        self.item = QGraphicsPixmapItem(pm)
        self.item.setTransformationMode(Qt.SmoothTransformation)
        self.item.setTransformOriginPoint(pm.width() / 2, pm.height() / 2)
        self.scene().addItem(self.item)
        self.scene().setSceneRect(self.item.sceneBoundingRect())
        self.fit()

    def fit(self):
        if self.item is not None:
            self.scene().setSceneRect(self.item.sceneBoundingRect())
            self.fitInView(self.item.sceneBoundingRect(), Qt.KeepAspectRatio)

    def rotate_by(self, deg: int):
        if self.item is None:
            return
        self.rotation = (self.rotation + deg) % 360
        self.item.setRotation(self.rotation)
        self.fit()

    def zoom(self, factor: float):
        self._user_zoom = True
        self.scale(factor, factor)

    def wheelEvent(self, event):  # noqa: N802
        d = event.angleDelta().y() or event.pixelDelta().y()
        if d:
            self.zoom(1.0015 ** d)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if not getattr(self, "_user_zoom", False):
            self.fit()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not getattr(self, "_user_zoom", False):
            self.fit()


class ImageBrowser(QWidget):
    """Seznam obrázků projektu + prohlížeč + poznámka k obrázku."""

    noteChanged = Signal(str, str)  # rel, text
    currentChanged = Signal(str)

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self.project = None
        self.current: str | None = None
        self._pages = 1
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        tb = QHBoxLayout()
        self.b_prev = QPushButton("◀")
        self.b_prev.setToolTip("Předchozí obrázek")
        self.b_prev.clicked.connect(lambda: self.step(-1))
        self.b_next = QPushButton("▶")
        self.b_next.setToolTip("Další obrázek")
        self.b_next.clicked.connect(lambda: self.step(1))
        self.view = ImageView()
        b_in = QPushButton("+")
        b_in.setToolTip("Přiblížit")
        b_in.clicked.connect(lambda: self.view.zoom(1.25))
        b_out = QPushButton("−")
        b_out.setToolTip("Oddálit")
        b_out.clicked.connect(lambda: self.view.zoom(0.8))
        b_fit = QPushButton("Celý")
        b_fit.setToolTip("Zobrazit celý obrázek")
        b_fit.clicked.connect(self._fit)
        b_rl = QPushButton("⟲")
        b_rl.setToolTip("Otočit doleva")
        b_rl.clicked.connect(lambda: self.view.rotate_by(-90))
        b_rr = QPushButton("⟳")
        b_rr.setToolTip("Otočit doprava")
        b_rr.clicked.connect(lambda: self.view.rotate_by(90))
        self.page = QSpinBox()
        self.page.setPrefix("str. ")
        self.page.setMinimum(1)
        self.page.setVisible(False)
        self.page.valueChanged.connect(self._page_changed)
        for w in (self.b_prev, self.b_next, b_in, b_out, b_fit, b_rl, b_rr, self.page):
            if isinstance(w, QPushButton):
                w.setMaximumWidth(48 if w.text() != "Celý" else 60)
            tb.addWidget(w)
        self.title = QLabel()
        tb.addWidget(self.title, 1)
        lay.addLayout(tb)

        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.IconMode)
        self.thumbs.setFlow(QListView.LeftToRight)
        self.thumbs.setWrapping(False)
        self.thumbs.setIconSize(QSize(72, 56))
        self.thumbs.setFixedHeight(96)
        self.thumbs.setMovement(QListView.Static)
        self.thumbs.currentItemChanged.connect(self._thumb_changed)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.view)
        notes = QWidget()
        nl = QVBoxLayout(notes)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.addWidget(QLabel("Poznámka k obrázku:"))
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Např. „bod 1005 je na náčrtu u plotu, ve výkresu chybí“")
        self.note.textChanged.connect(self._note_edited)
        nl.addWidget(self.note)
        split.addWidget(notes)
        split.setSizes([500, 90 if not compact else 60])
        lay.addWidget(self.thumbs)
        lay.addWidget(split, 1)
        self._loading = False

    def _fit(self):
        self.view._user_zoom = False
        self.view.fit()

    def set_project(self, project):
        self.project = project
        self.refresh()

    def images(self) -> list[str]:
        if self.project is None:
            return []
        return [a.rel for a in self.project.attachments("obrazky") if a.path.suffix.lower() in IMAGE_EXT]

    def refresh(self):
        cur = self.current
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for rel in self.images():
            path = self.project.root / rel
            it = QListWidgetItem(Path(rel).name)
            it.setData(Qt.UserRole, rel)
            try:
                pm = load_pixmap(path)
                if not pm.isNull():
                    it.setIcon(QIcon(pm.scaled(144, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            except OSError:
                pass
            it.setToolTip(rel)
            self.thumbs.addItem(it)
        self.thumbs.blockSignals(False)
        rels = self.images()
        if cur in rels:
            self.show_image(cur)
        elif rels:
            self.show_image(rels[0])
        else:
            self.current = None
            self.view.set_pixmap(None)
            self.title.setText("Žádné obrázky – přidejte je tlačítkem „Přidat obrázky…“ nebo přetažením.")
            self._loading = True
            self.note.setPlainText("")
            self._loading = False

    def show_image(self, rel: str):
        if self.project is None:
            return
        self.current = rel
        path = self.project.root / rel
        self._pages = pdf_page_count(path) if path.suffix.lower() == ".pdf" else 1
        self.page.blockSignals(True)
        self.page.setMaximum(max(1, self._pages))
        self.page.setValue(1)
        self.page.setVisible(self._pages > 1)
        self.page.blockSignals(False)
        self.view.set_pixmap(load_pixmap(path) if path.exists() else None)
        idx = self.images().index(rel) if rel in self.images() else -1
        self.title.setText(f"{Path(rel).name}  ({idx + 1}/{len(self.images())})")
        self._loading = True
        self.note.setPlainText(self.project.image_note(rel))
        self._loading = False
        for i in range(self.thumbs.count()):
            if self.thumbs.item(i).data(Qt.UserRole) == rel:
                self.thumbs.blockSignals(True)
                self.thumbs.setCurrentRow(i)
                self.thumbs.blockSignals(False)
        self.currentChanged.emit(rel)

    def _page_changed(self, v: int):
        if self.current:
            self.view.set_pixmap(load_pixmap(self.project.root / self.current, v - 1))

    def _thumb_changed(self, cur, prev):
        if cur is not None:
            self.show_image(cur.data(Qt.UserRole))

    def step(self, d: int):
        imgs = self.images()
        if not imgs:
            return
        i = imgs.index(self.current) if self.current in imgs else -1
        self.show_image(imgs[(i + d) % len(imgs)])

    def _note_edited(self):
        if self._loading or self.project is None or not self.current:
            return
        self.project.set_image_note(self.current, self.note.toPlainText())
        self.noteChanged.emit(self.current, self.note.toPlainText())

    def sync_note(self, rel: str, text: str):
        if rel == self.current and self.note.toPlainText() != text:
            self._loading = True
            self.note.setPlainText(text)
            self._loading = False
