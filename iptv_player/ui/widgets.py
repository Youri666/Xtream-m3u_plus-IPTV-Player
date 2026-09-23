"""Reusable Qt widgets shared by the application screens."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidget, QListWidgetItem


class KeyboardNavigableListWidget(QListWidget):
    """Give catalog lists explicit keyboard activation and column switching."""

    keyboardSelected = pyqtSignal(QListWidgetItem)
    keyboardActivated = pyqtSignal(QListWidgetItem)
    itemsReordered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tab_target = None

    def set_tab_target(self, target):
        self._tab_target = target

    def dropEvent(self, event):
        """Report a completed internal row move to the owning catalog view."""
        previous_order = [id(self.item(row)) for row in range(self.count())]
        super().dropEvent(event)
        current_order = [id(self.item(row)) for row in range(self.count())]
        if current_order != previous_order:
            self.itemsReordered.emit()

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

