"""Verify content-sized History columns and automatic overflow handling."""

import ast
import configparser
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QByteArray
from PyQt5.QtTest import QTest

from iptv_player.config.ini import write_config_file
from iptv_player.ui.history import HistoryTreeWidget


def layout_methods():
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'IPTVPlayerApp')
    names = {'init_history_tab', 'save_window_layout', 'restore_window_layout',
             '_encoded_widget_state', '_decoded_widget_state'}
    namespace = dict(Qt=Qt, QtWidgets=QtWidgets, QByteArray=QByteArray,
                     QGroupBox=QtWidgets.QGroupBox, QVBoxLayout=QtWidgets.QVBoxLayout,
                     HistoryTreeWidget=HistoryTreeWidget, configparser=configparser,
                     write_config_file=write_config_file)
    module = ast.Module(body=[n for n in cls.body if isinstance(n, ast.FunctionDef)
                             and n.name in names], type_ignores=[])
    exec(compile(module, str(source), 'exec'), namespace)
    return {name: namespace[name] for name in names}


class HistoryLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def harness(self, filename):
        harness = type('LayoutHarness', (QtWidgets.QWidget,), layout_methods())()
        harness.user_data_file = str(filename)
        harness.history_tab_layout = QtWidgets.QVBoxLayout(harness)
        harness.refresh_history_tab = Mock()
        harness._show_history_context_menu = Mock()
        harness._history_item_activated = Mock()
        harness._ensure_window_is_visible = Mock()
        for name in ('live_splitter', 'movies_splitter', 'series_splitter'):
            setattr(harness, name, QtWidgets.QSplitter())
        harness.init_history_tab()
        self.addCleanup(harness.close)
        return harness

    def test_columns_auto_size_and_do_not_persist_widths(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'userdata.ini'
            filename.write_text('[Theme]\nmode=Dark\n', encoding='utf-8')
            original = self.harness(filename)
            for tree in original.history_widgets.values():
                self.assertEqual(tree.header().sectionResizeMode(0), QtWidgets.QHeaderView.ResizeToContents)
                self.assertEqual(tree.header().sectionResizeMode(1), QtWidgets.QHeaderView.ResizeToContents)
            original.save_window_layout()
            restored = self.harness(filename)
            restored.restore_window_layout()
            self.assertIn('mode = Dark', filename.read_text(encoding='utf-8'))
            self.assertNotIn('history_movies_header', filename.read_text(encoding='utf-8'))

    def test_scroll_bars_appear_only_when_content_overflows(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = self.harness(Path(directory) / 'userdata.ini')
            tree = harness.history_widgets['Movies']
            tree.setParent(None)
            self.addCleanup(tree.close)
            tree.resize(400, 180)
            tree.addTopLevelItem(QtWidgets.QTreeWidgetItem(['2026-10-02 14:02', 'Short']))
            tree.show()
            self.app.processEvents()
            self.assertFalse(tree.horizontalScrollBar().isVisible())
            self.assertFalse(tree.verticalScrollBar().isVisible())
            for i in range(30):
                tree.addTopLevelItem(QtWidgets.QTreeWidgetItem(['date', 'Long episode title ' * 12]))
            QTest.qWait(30)
            self.assertTrue(tree.horizontalScrollBar().isVisible())
            self.assertTrue(tree.verticalScrollBar().isVisible())

    def test_expanding_series_resizes_to_episode_titles(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = self.harness(Path(directory) / 'userdata.ini')
            tree = harness.history_widgets['Series']
            tree.setParent(None)
            self.addCleanup(tree.close)
            tree.resize(500, 200)
            parent = QtWidgets.QTreeWidgetItem(['2026-10-02 14:02', 'Series'])
            parent.addChild(QtWidgets.QTreeWidgetItem(['2026-10-02 13:00', 'Long episode title ' * 12]))
            tree.addTopLevelItem(parent)
            tree.show()
            QTest.qWait(30)
            width = tree.columnWidth(1)
            self.assertFalse(tree.horizontalScrollBar().isVisible())
            parent.setExpanded(True)
            QTest.qWait(30)
            self.assertGreater(tree.columnWidth(1), width)
            self.assertTrue(tree.horizontalScrollBar().isVisible())
            parent.setExpanded(False)
            QTest.qWait(30)
            self.assertEqual(tree.columnWidth(1), width)
            self.assertFalse(tree.horizontalScrollBar().isVisible())

    def test_titles_fill_viewport_for_empty_and_short_lists_after_resize(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = self.harness(Path(directory) / 'userdata.ini')
            tree = harness.history_widgets['Movies']
            tree.setParent(None)
            self.addCleanup(tree.close)
            tree.show()
            for populated in (False, True):
                if populated:
                    tree.addTopLevelItem(QtWidgets.QTreeWidgetItem(['2026-10-02 14:02', 'Short']))
                for width in (650, 900, 700):
                    tree.resize(width, 180)
                    QTest.qWait(30)
                    self.assertEqual(tree.columnWidth(0) + tree.columnWidth(1), tree.viewport().width())
                    self.assertFalse(tree.horizontalScrollBar().isVisible())
