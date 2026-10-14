"""Smooth information-panel artwork rendered from its original source."""

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QLabel


class ArtworkLabel(QLabel):
    """Keep original pixels and rerender when moving between screen densities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = QPixmap()
        self._svg = None
        self._logical_size = QSize()
        self._rendered_dpr = None

    def setPixmap(self, pixmap):
        """Keep supplied artwork at its logical width, including status circles."""
        if pixmap.isNull():
            self.set_artwork(pixmap, width=1)
            return
        self.set_artwork(pixmap, width=round(pixmap.width() / pixmap.devicePixelRatioF()))

    def set_artwork(self, source, *, width=None, height=None):
        """Scale an original pixmap to one logical dimension, keeping proportions."""
        self._source = QPixmap(source)
        self._svg = None
        self._set_artwork_size(self._source.size(), width, height)

    def set_artwork_file(self, filename, *, width=None, height=None):
        """Render vector files directly at the target screen's physical resolution."""
        if str(filename).lower().endswith(".svg"):
            self._svg = QSvgRenderer(str(filename))
            self._source = QPixmap()
            self._set_artwork_size(self._svg.defaultSize(), width, height)
        else:
            self.set_artwork(QPixmap(str(filename)), width=width, height=height)

    def _set_artwork_size(self, original, width, height):
        if original.isEmpty():
            self._logical_size = QSize()
            self.clear()
            return
        if width is not None:
            self._logical_size = QSize(int(width), max(1, round(original.height() * width / original.width())))
        else:
            self._logical_size = QSize(max(1, round(original.width() * height / original.height())), int(height))
        self._rendered_dpr = None
        self._render_artwork()

    def _render_artwork(self):
        if self._logical_size.isEmpty():
            return
        dpr = self.devicePixelRatioF()
        physical = QSize(max(1, round(self._logical_size.width() * dpr)),
                         max(1, round(self._logical_size.height() * dpr)))
        if self._svg is not None:
            pixmap = QPixmap(physical)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            self._svg.render(painter)
            painter.end()
        else:
            pixmap = self._source.scaled(physical, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pixmap.setDevicePixelRatio(dpr)
        self._rendered_dpr = dpr
        super().setPixmap(pixmap)

    def paintEvent(self, event):
        if self._rendered_dpr != self.devicePixelRatioF():
            self._render_artwork()
        super().paintEvent(event)
