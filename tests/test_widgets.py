import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

from iptv_player.ui.widgets import KeyboardNavigableListWidget


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


if __name__ == "__main__":
    unittest.main()
