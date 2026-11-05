"""Size the shared information panel to its visible content and video bounds."""
import math

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QTextBrowser, QStyle


def information_panel_size(panel, title, body, available):
    """Measure content without imposing a fixed minimum or resizing the player."""
    panel.ensurePolished()
    title.ensurePolished()
    body.ensurePolished()
    margins = panel.layout().contentsMargins()
    horizontal = margins.left() + margins.right() + 2 * panel.frameWidth()
    vertical = (margins.top() + margins.bottom() + 2 * panel.frameWidth()
                + title.sizeHint().height() + panel.layout().spacing())
    title_width = title.sizeHint().width()
    frame = 2 * body.frameWidth()
    scrollbar = body.style().pixelMetric(QStyle.PM_ScrollBarExtent)
    max_width, max_height = max(1, available.width()), max(1, available.height())
    if isinstance(body, QTextBrowser):
        document = body.document().clone()
        document.setDefaultFont(body.font())
        document.documentLayout().setPaintDevice(body.viewport())
        document.setTextWidth(-1)
        document.adjustSize()
        width = min(max_width, max(title_width, math.ceil(document.idealWidth()) + frame) + horizontal)
        document.setTextWidth(max(1, width - horizontal - frame))
        height = math.ceil(document.size().height()) + frame + vertical
        if height > max_height:
            # Reserve the vertical bar before wrapping, avoiding a horizontal bar
            # caused solely by its appearance at the height limit.
            width = min(max_width, width + scrollbar)
            document.setTextWidth(max(1, width - horizontal - frame - scrollbar))
            height = math.ceil(document.size().height()) + frame + vertical
        document.deleteLater()
    else:
        header = body.header()
        columns = [QFontMetrics(header.font()).horizontalAdvance(
            body.headerItem().text(column)) + 16 for column in range(body.columnCount())]
        rows_height = 0
        section_width = 0
        index = body.model().index(0, 0)
        while index.isValid():
            item = body.itemFromIndex(index)
            depth, parent = 1, item.parent()
            while parent is not None:
                depth += 1
                parent = parent.parent()
            rows_height += max(body.sizeHintForIndex(index).height(),
                               QFontMetrics(item.font(0)).height())
            for column in range(body.columnCount()):
                text_width = QFontMetrics(item.font(column)).horizontalAdvance(item.text(column)) + 12
                if column == 0:
                    text_width += depth * body.indentation()
                if body.isFirstColumnSpanned(index.row(), index.parent()):
                    section_width = max(section_width, text_width)
                    break
                columns[column] = max(columns[column], text_width)
            index = body.indexBelow(index)
        header_height = 0 if header.isHidden() else header.sizeHint().height()
        width = max(title_width, section_width, sum(columns)) + frame + horizontal
        height = rows_height + header_height + frame + vertical
        if height > max_height:
            width += scrollbar
        if width > max_width:
            height += scrollbar
        # Keep the value column wide enough for its content. Stretching alone
        # would truncate long values instead of enabling horizontal scrolling.
        for column, content_width in enumerate(columns):
            header.resizeSection(column, content_width)
    return QSize(max(1, min(max_width, width)), max(1, min(max_height, height)))
