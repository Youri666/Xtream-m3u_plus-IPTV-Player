import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtGui, QtWidgets

from iptv_player.ui.widgets import (
    KeyboardNavigableListWidget,
    context_selected_items,
)


class KeyboardNavigableListWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_each_successive_row_move_emits_reorder_signal(self):
        widget = KeyboardNavigableListWidget()
        widget.addItems(["One", "Two", "Three"])
        reorder_count = []
        widget.itemsReordered.connect(lambda: reorder_count.append(1))

        model = widget.model()
        root = QtCore.QModelIndex()
        self.assertTrue(model.moveRow(root, 0, root, 3))
        self.assertTrue(model.moveRow(root, 1, root, 0))

        self.assertEqual(reorder_count, [1, 1])
        self.assertEqual(
            [widget.item(row).text() for row in range(widget.count())],
            ["Three", "Two", "One"],
        )

    def test_compact_rows_follow_font_changes_and_preserve_separator_height(self):
        widget = KeyboardNavigableListWidget()
        widget.addItems(['Channel', 'Separator'])
        widget.item(1).setSizeHint(QtCore.QSize(0, 9))
        for pixels in (14, 28):
            font = widget.font()
            font.setPixelSize(pixels)
            widget.setFont(font)
            widget.doItemsLayout()
            metrics = QtGui.QFontMetrics(font)
            bounds = metrics.tightBoundingRect('AgÉgjÀÇ').united(metrics.tightBoundingRect('Channel'))
            self.assertEqual(widget.sizeHintForRow(0), bounds.height() + 2)
            self.assertEqual(widget.sizeHintForRow(1), 9)

    def test_compact_rows_keep_real_navigation_icons_visible(self):
        widget = KeyboardNavigableListWidget()
        widget.setIconSize(QtCore.QSize(24, 24))
        item = QtWidgets.QListWidgetItem('Go back')
        pixmap = QtGui.QPixmap(24, 24)
        pixmap.fill(QtCore.Qt.black)
        item.setIcon(QtGui.QIcon(pixmap))
        widget.addItem(item)
        widget.doItemsLayout()
        self.assertGreaterEqual(widget.sizeHintForRow(0), 26)

    def test_spacing_diagnostic_runs_when_visible_list_is_populated_later(self):
        widget = KeyboardNavigableListWidget()
        try:
            with self.assertLogs(level='DEBUG') as captured:
                widget.show()
                self.app.processEvents()
                self.assertIsNone(widget._last_spacing_diagnostic)
                widget.addItems(['Private title one', 'Private title two'])
                self.app.processEvents()
                self.app.processEvents()
                self.assertIsNotNone(widget._last_spacing_diagnostic)
                widget.addItem('Private title three')
                self.app.processEvents()
            self.assertEqual(len(captured.output), 1)
            self.assertIn('actual_height=', captured.output[0])
            self.assertNotIn('Private title', captured.output[0])
        finally:
            widget.close()
            widget.deleteLater()

    def test_context_menu_preserves_existing_multi_selection(self):
        widget = KeyboardNavigableListWidget()
        widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        widget.addItems(["One", "Two", "Three"])
        widget.item(0).setSelected(True)
        widget.item(2).setSelected(True)

        selected = context_selected_items(widget, widget.item(2))

        self.assertEqual([item.text() for item in selected], ["One", "Three"])

    def test_context_menu_replaces_selection_for_unselected_row(self):
        widget = KeyboardNavigableListWidget()
        widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        widget.addItems(["One", "Two", "Three"])
        widget.item(0).setSelected(True)
        widget.item(2).setSelected(True)

        selected = context_selected_items(widget, widget.item(1))

        self.assertEqual([item.text() for item in selected], ["Two"])


if __name__ == "__main__":
    unittest.main()
