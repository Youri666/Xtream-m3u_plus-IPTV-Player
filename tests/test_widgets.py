import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

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
