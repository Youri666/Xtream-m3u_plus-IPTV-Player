"""Series list navigation state regression tests."""

import ast
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QListView, QListWidget, QListWidgetItem


def series_navigation_methods():
    """Extract state helpers without constructing the complete application."""
    source = Path(__file__).resolve().parents[1] / "IPTVPlayer.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    app_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "IPTVPlayerApp"
    )
    names = {
        "_scroll_to_catalog_item",
        "_capture_series_view_state",
        "_restore_series_view_state",
        "_navigate_series_back",
    }
    module = ast.Module(
        body=[
            node for node in app_class.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ],
        type_ignores=[],
    )
    namespace = {
        "Qt": Qt, "QTimer": QTimer, "QtWidgets": QtWidgets,
        "QListView": QListView,
    }
    exec(compile(module, str(source), "exec"), namespace)
    return {name: namespace[name] for name in names}


class SeriesNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reveals_history_selection_before_first_batched_layout(self):
        harness = type("SeriesHarness", (), series_navigation_methods())()
        series_list = QListWidget()
        series_list.resize(300, 120)
        series_list.setLayoutMode(QListView.Batched)
        series_list.setBatchSize(20)
        for row in range(600):
            series_list.addItem(f"Series {row}")
        series_list.show()
        selected_item = series_list.item(550)
        series_list.setCurrentItem(selected_item)
        harness._scroll_to_catalog_item(series_list, selected_item)
        self.app.processEvents()
        self.assertTrue(
            series_list.viewport().rect().intersects(
                series_list.visualItemRect(selected_item)
            )
        )
        self.assertEqual(series_list.layoutMode(), QListView.Batched)
        harness.streaming_list_widgets = {"Series": series_list}
        harness._series_view_states = {}
        harness.series_navigation_level = 0
        harness._capture_series_view_state(0)
        series_list.clear()
        for row in range(600):
            series_list.addItem(f"Series {row}")
        harness._restore_series_view_state(0)
        for _ in range(100):
            self.app.processEvents()
        self.assertGreater(harness._series_view_states[0]["scroll"], 0)
        self.assertEqual(series_list.currentRow(), 550)
        self.assertTrue(
            series_list.viewport().rect().intersects(
                series_list.visualItemRect(series_list.currentItem())
            )
        )
        series_list.close()

    def test_restores_selected_series_and_scroll_position(self):
        methods = series_navigation_methods()
        harness = type("SeriesHarness", (), methods)()
        series_list = QListWidget()
        series_list.resize(300, 120)
        harness.streaming_list_widgets = {"Series": series_list}
        harness._series_view_states = {}
        harness.series_navigation_level = 0

        for series_id in range(40):
            item = QListWidgetItem(f"Series {series_id}")
            item.setData(Qt.UserRole, {"series_id": series_id})
            series_list.addItem(item)
        series_list.show()
        self.app.processEvents()
        series_list.setCurrentRow(30)
        series_list.verticalScrollBar().setValue(24)
        harness._capture_series_view_state(0)

        series_list.clear()
        for series_id in range(40):
            item = QListWidgetItem(f"Series {series_id}")
            item.setData(Qt.UserRole, {"series_id": series_id})
            series_list.addItem(item)
        self.app.processEvents()
        harness._restore_series_view_state(0)

        self.assertEqual(
            series_list.currentItem().data(Qt.UserRole)["series_id"], 30
        )
        self.assertEqual(series_list.verticalScrollBar().value(), 24)
        series_list.close()

    def test_back_navigation_moves_up_exactly_one_level(self):
        methods = series_navigation_methods()
        harness = type("SeriesHarness", (), methods)()
        harness.series_navigation_level = 2
        harness.prev_clicked_streaming_item = object()
        harness.prev_double_clicked_streaming_item = object()
        restored_levels = []
        harness.go_back_to_level = restored_levels.append

        harness._navigate_series_back()

        self.assertEqual(harness.series_navigation_level, 1)
        self.assertEqual(restored_levels, [1])
        self.assertIsNone(harness.prev_clicked_streaming_item)
        self.assertIsNone(harness.prev_double_clicked_streaming_item)


if __name__ == "__main__":
    unittest.main()
