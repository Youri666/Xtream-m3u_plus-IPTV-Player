import os
import unittest
from unittest.mock import patch

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
            bounds = metrics.tightBoundingRect('AgÉgjÀÇ')
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

    def test_large_lists_share_one_reference_measurement_per_font(self):
        widgets = [KeyboardNavigableListWidget(), KeyboardNavigableListWidget()]
        delegate = widgets[0].itemDelegate()
        delegate._font_bounds.clear()
        with patch.object(type(delegate), '_measure_reference_bounds',
                          wraps=delegate._measure_reference_bounds) as measure:
            for widget in widgets:
                widget.addItems([f'Film {row}' for row in range(1000)])
                for _ in range(2):
                    for row in range(widget.count()):
                        widget.sizeHintForRow(row)
            self.assertEqual(measure.call_count, 1)
            widgets[0].item(5).setText('Updated title')
            widgets[0].sizeHintForRow(5)
            self.assertEqual(measure.call_count, 1)
            font = widgets[0].font()
            font.setPixelSize(30)
            widgets[0].setFont(font)
            widgets[0].sizeHintForRow(0)
            self.assertEqual(measure.call_count, 2)

    def test_colour_only_theme_changes_reuse_font_measurements(self):
        from iptv_player.ui.theme import apply_application_theme
        apply_application_theme(self.app, 'Light')
        widget = KeyboardNavigableListWidget()
        sheet = 'QListWidget::item { padding: 1px 0; }'
        widget.setStyleSheet(sheet)
        widget.addItems(['One', 'Édition complète', 'Three'])
        delegate = widget.itemDelegate()
        delegate._font_bounds.clear()
        with patch.object(type(delegate), '_measure_reference_bounds',
                          wraps=delegate._measure_reference_bounds) as measure:
            initial = [widget.sizeHintForRow(row) for row in range(widget.count())]
            for theme in ('Dark', 'Light'):
                apply_application_theme(self.app, theme)
                widget.setStyleSheet('')
                widget.setPalette(self.app.palette())
                widget.setStyleSheet(sheet)
                self.assertEqual([widget.sizeHintForRow(row) for row in range(widget.count())], initial)
            self.assertEqual(measure.call_count, 1)

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
