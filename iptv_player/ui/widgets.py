"""Reusable Qt widgets shared by the application screens."""

import math
import logging

from PyQt5.QtCore import Qt, QPointF, QItemSelectionModel, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QPalette
from PyQt5.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QStyledItemDelegate, QStyleOptionViewItem,
    QApplication, QStyle,
)


class CompactListDelegate(QStyledItemDelegate):
    """Keep single-line rows compact regardless of the platform's item padding."""

    @staticmethod
    def _ink_bounds(option):
        # Include common accents and descenders for stable Latin row heights,
        # then extend for taller glyphs in the actual title (including fallback fonts).
        metrics = option.fontMetrics
        return metrics.tightBoundingRect('AgÉgjÀÇ').united(
            metrics.tightBoundingRect(option.text))

    def sizeHint(self, option, index):
        explicit_size = index.data(Qt.SizeHintRole)
        if explicit_size is not None:
            return explicit_size  # Preserve category separators and custom rows.
        size = super().sizeHint(option, index)
        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        height = self._ink_bounds(item_option).height()
        if not item_option.icon.isNull():
            height = max(height, item_option.icon.actualSize(item_option.decorationSize).height())
        # Qt font metrics are logical pixels: do not multiply by the screen DPR.
        size.setHeight(height + 2)
        return size

    def paint(self, painter, option, index):
        if index.data(Qt.SizeHintRole) is not None:
            return super().paint(painter, option, index)
        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        style = item_option.widget.style() if item_option.widget else QApplication.style()
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, item_option,
                                        item_option.widget)
        text = item_option.fontMetrics.elidedText(
            item_option.text, item_option.textElideMode, max(0, text_rect.width() - 4))
        bounds = self._ink_bounds(item_option)
        item_option.text = ''
        # Let Qt retain native selection, focus, checkboxes and icon rendering.
        style.drawControl(QStyle.CE_ItemViewItem, item_option, painter, item_option.widget)
        painter.save()
        painter.setClipRect(option.rect, Qt.IntersectClip)
        painter.setFont(item_option.font)
        group = (QPalette.Disabled if not item_option.state & QStyle.State_Enabled
                 else QPalette.Normal if item_option.state & QStyle.State_Active
                 else QPalette.Inactive)
        role = (QPalette.HighlightedText if item_option.state & QStyle.State_Selected
                else QPalette.Text)
        painter.setPen(item_option.palette.color(group, role))
        x = text_rect.left() + 2
        if item_option.direction == Qt.RightToLeft:
            x = text_rect.right() - 2 - item_option.fontMetrics.horizontalAdvance(text)
        # Center the ink rather than the font's potentially oversized ascent/descent.
        baseline = option.rect.y() + (option.rect.height() - bounds.height()) / 2 - bounds.y()
        painter.drawText(QPointF(x, baseline), text)
        painter.restore()


class CategorySeparator(QWidget):
    """Paint a one-device-pixel separator at fractional display scales."""

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(self.palette().color(QPalette.Mid))
        pen.setWidth(0)
        painter.setPen(pen)
        # Align the cosmetic pen with a physical pixel center, regardless of
        # the row's position or the screen's fractional device pixel ratio.
        transform = painter.deviceTransform()
        center = transform.map(QPointF(0, self.height() / 2))
        inverse, invertible = transform.inverted()
        if invertible:
            y = inverse.map(QPointF(center.x(), math.floor(center.y()) + 0.5)).y()
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        painter.end()


def context_selected_items(list_widget, clicked_item):
    """Preserve a multi-selection when its context menu is opened."""
    if not clicked_item.isSelected():
        list_widget.clearSelection()
        clicked_item.setSelected(True)
    list_widget.setCurrentRow(
        list_widget.row(clicked_item), QItemSelectionModel.NoUpdate
    )
    return sorted(list_widget.selectedItems(), key=list_widget.row)


class KeyboardNavigableListWidget(QListWidget):
    """Give catalog lists explicit keyboard activation and column switching."""

    keyboardSelected = pyqtSignal(QListWidgetItem)
    keyboardActivated = pyqtSignal(QListWidgetItem)
    itemsReordered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(CompactListDelegate(self))
        self.setSpacing(0)
        self._tab_target = None
        self._last_spacing_diagnostic = None
        self._spacing_diagnostic_timer = QTimer(self)
        self._spacing_diagnostic_timer.setSingleShot(True)
        self._spacing_diagnostic_timer.timeout.connect(self._log_row_geometry)
        # Lists often become visible before asynchronous catalogue loading ends.
        # Coalesce insertion bursts and measure after Qt has laid out the rows.
        for signal in (self.model().rowsInserted, self.model().modelReset,
                       self.model().layoutChanged, self.model().dataChanged):
            signal.connect(self._schedule_spacing_diagnostic)
        # QAbstractItemModel provides the authoritative notification for an
        # internal row move. Comparing temporary PyQt wrapper identities in
        # dropEvent is unreliable because their memory addresses are reused.
        self.model().rowsMoved.connect(
            lambda *_args: self.itemsReordered.emit()
        )

    def set_tab_target(self, target):
        self._tab_target = target

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_spacing_diagnostic()

    def _schedule_spacing_diagnostic(self, *_args):
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            self._spacing_diagnostic_timer.start(0)

    def _log_row_geometry(self):
        """Log actual list geometry once per configuration, without item text."""
        if not logging.getLogger().isEnabledFor(logging.DEBUG):
            return
        # Skip separators and special rows so the sample represents plain text.
        item = next((self.item(row) for row in range(min(self.count(), 30))
                     if self.item(row).sizeHint().isEmpty()
                     and self.item(row).icon().isNull()), None)
        if item is None:
            return
        option = QStyleOptionViewItem()
        option.initFrom(self)
        self.itemDelegate().initStyleOption(option, self.indexFromItem(item))
        metrics = option.fontMetrics
        geometry = (option.font.toString(), self.logicalDpiY(), self.devicePixelRatioF(),
                    metrics.height(), metrics.ascent(), metrics.descent(), metrics.leading(),
                    metrics.tightBoundingRect('AgÉgj').height(),
                    self.itemDelegate().sizeHint(option, self.indexFromItem(item)).height(),
                    self.visualItemRect(item).height(), self.spacing())
        if geometry == self._last_spacing_diagnostic:
            return
        self._last_spacing_diagnostic = geometry
        logging.debug('List row geometry: font=%r; dpi_y=%s; dpr=%s; font_height=%s; '
                      'ascent=%s; descent=%s; leading=%s; glyph_height=%s; '
                      'delegate_height=%s; actual_height=%s; spacing=%s', *geometry)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            current_item = self.currentItem()
            if current_item is not None:
                self.keyboardActivated.emit(current_item)
            event.accept()
            return

        if event.key() in (Qt.Key_Tab, Qt.Key_Backtab) and self._tab_target is not None:
            if self._tab_target.currentItem() is None and self._tab_target.count():
                self._tab_target.setCurrentRow(0)
                self._tab_target.keyboardSelected.emit(self._tab_target.currentItem())
            self._tab_target.setFocus(Qt.TabFocusReason)
            event.accept()
            return

        navigation_keys = (
            Qt.Key_Up,
            Qt.Key_Down,
            Qt.Key_Home,
            Qt.Key_End,
            Qt.Key_PageUp,
            Qt.Key_PageDown,
        )
        if event.key() in navigation_keys:
            previous_item = self.currentItem()
            super().keyPressEvent(event)
            current_item = self.currentItem()
            if current_item is not None and current_item is not previous_item:
                self.keyboardSelected.emit(current_item)
            return

        super().keyPressEvent(event)

