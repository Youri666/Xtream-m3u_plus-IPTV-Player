"""Regression coverage for independent category caches and retained searches."""

import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QLineEdit, QListWidget, QListWidgetItem


def methods():
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'IPTVPlayerApp')
    names = {'_favorite_items_reordered', '_apply_active_stream_search'}
    namespace = {'Qt': Qt, 'reorder_custom_category': Mock(), 'reorder_favorites': Mock()}
    module = ast.Module(body=[node for node in cls.body
                             if isinstance(node, ast.FunctionDef) and node.name in names],
                        type_ignores=[])
    exec(compile(module, str(source), 'exec'), namespace)
    return {name: namespace[name] for name in names}


class CatalogFilterStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_custom_reorder_does_not_replace_favorites_cache(self):
        harness = type('Harness', (), methods())()
        rows = QListWidget()
        entry = {'stream_id': 42, 'name': 'Movie'}
        row = QListWidgetItem('Movie')
        row.setData(Qt.UserRole, entry)
        rows.addItem(row)
        harness.streaming_list_widgets = {'Movies': rows}
        harness._favorite_reordering_enabled = Mock(return_value=True)
        harness._selected_category = Mock(return_value=('TEST', 'custom:test'))
        harness._custom_category_id = Mock(return_value='test')
        harness._category_view_key = Mock(return_value=('custom:test', False, 0))
        harness.favorites_file = 'unused'
        harness.currently_loaded_streams = {}
        favorites = [{'stream_id': 99}]
        harness.category_view_cache = {'Movies': {'favorites': favorites}}
        harness.active_category_view_key = {}
        harness._favorite_items_reordered('Movies')
        self.assertEqual(harness.category_view_cache['Movies']['favorites'], favorites)
        self.assertEqual(harness.category_view_cache['Movies'][('custom:test', False, 0)], [entry])

    def test_reapplies_existing_query_for_every_content_tab(self):
        harness = type('Harness', (), methods())()
        harness.search_in_list = Mock()
        harness.streaming_search_bars = {tab: QLineEdit('Batman')
                                        for tab in ('LIVE', 'Movies', 'Series')}
        for tab in harness.streaming_search_bars:
            harness._apply_active_stream_search(tab)
            harness.search_in_list.assert_called_with('streaming', tab, 'Batman')
            self.assertEqual(harness.streaming_search_bars[tab].text(), 'Batman')
