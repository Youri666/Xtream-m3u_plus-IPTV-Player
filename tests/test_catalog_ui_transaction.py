"""Verify that list replacement cannot dispatch a destructive queued callback."""

import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt, QTimer
from PyQt5 import QtWidgets


def catalog_methods():
    # Extract the production methods without starting VLC or loading user settings.
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    app_class = next(node for node in tree.body
                     if isinstance(node, ast.ClassDef)
                     and node.name == 'IPTVPlayerApp')
    names = {'_replace_streaming_list_items', 'set_progress_bar',
             'set_progress_state', 'set_progress_text', 'favorite_button_pressed'}
    module = ast.Module(body=[node for node in app_class.body
                             if isinstance(node, ast.FunctionDef)
                             and node.name in names], type_ignores=[])
    namespace = {'Qt': Qt, 'QtWidgets': QtWidgets, 'set_favorite': Mock()}
    exec(compile(module, str(source), 'exec'), namespace)
    return {name: namespace[name] for name in names}


class CatalogTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_queued_clear_runs_only_after_complete_replacement(self):
        harness = type('CatalogHarness', (), catalog_methods())()
        streams = QtWidgets.QListWidget()
        categories = QtWidgets.QListWidget()
        harness.streaming_list_widgets = {'Movies': streams}
        harness.category_list_widgets = {'Movies': categories}
        harness.progress_bar = QtWidgets.QProgressBar()
        observed_counts = []

        def queued_clear():
            observed_counts.append(streams.count())
            streams.clear()

        entries = [{'name': str(index)} for index in range(2501)]
        QTimer.singleShot(0, queued_clear)
        harness._replace_streaming_list_items('Movies', entries)
        self.assertEqual(observed_counts, [])
        self.assertEqual(streams.count(), len(entries))
        self.assertEqual(streams.item(2500).data(Qt.UserRole), entries[-1])
        self.assertTrue(categories.isEnabled())
        self.assertTrue(streams.updatesEnabled())
        self.app.processEvents()
        self.assertEqual(observed_counts, [len(entries)])
        self.assertEqual(streams.count(), 0)

    def test_nested_series_removal_returns_to_favorites_root(self):
        for level in (1, 2):
            with self.subTest(level=level):
                harness = type('CatalogHarness', (), catalog_methods())()
                series = {'series_id': 42, 'name': 'Show', 'favorite': False}
                streams = QtWidgets.QListWidget()
                streams.addItem('Go back')
                streams.addItem('Season or episode')
                streams.item(1).setData(Qt.UserRole, {'id': 123})
                harness.streaming_list_widgets = {'Series': streams}
                harness.series_navigation_level = level
                harness.current_series_entry = series
                harness.entries_per_stream_type = {'Series': [series]}
                harness.currently_loaded_streams = {'Series': [series]}
                harness.category_view_cache = {'Series': {}}
                harness.category_item_cache = {'Series': {}}
                harness.active_category_view_key = {'Series': ('favorites',)}
                harness.fav_categories_text = 'Favorites'
                harness._selected_category = Mock(return_value=('Favorites', None))
                harness._entries_for_category_view = Mock(
                    side_effect=lambda *args: [series] if series['favorite'] else []
                )
                categories = QtWidgets.QListWidget()
                categories.addItem('Favorites')
                categories.setCurrentRow(0)
                harness.category_list_widgets = {'Series': categories}
                harness.prev_clicked_category_item = {'Series': categories.item(0)}
                navigations = []

                def navigate_to_root(item):
                    self.assertIsNone(harness.prev_clicked_category_item['Series'])
                    navigations.append(item.text())
                    harness.series_navigation_level = 0
                    streams.clear()

                categories.itemClicked.connect(navigate_to_root)
                harness.favorites_file = 'unused.json'
                harness._refresh_category_count_labels = Mock()
                harness.animate_progress = Mock()
                info_box = Mock()
                harness.favorite_button_pressed('Series', info_box)
                self.assertTrue(series['favorite'])
                self.assertEqual(streams.count(), 2)
                self.assertEqual(navigations, [])
                streams.setCurrentRow(1)
                harness.favorite_button_pressed('Series', info_box)
                self.assertFalse(series['favorite'])
                self.assertEqual(streams.count(), 0)
                self.assertEqual(navigations, ['Favorites'])
                self.assertEqual(harness.series_navigation_level, 0)
                self.assertEqual(harness.currently_loaded_streams['Series'], [])
                harness.animate_progress.assert_not_called()
                saved = harness.favorite_button_pressed.__func__.__globals__['set_favorite']
                self.assertEqual(saved.call_count, 2)
                saved.assert_called_with('unused.json', 'Series', 42, False)

    def test_remove_favorite_refreshes_root_even_when_cache_key_is_invalidated(self):
        harness = type('CatalogHarness', (), catalog_methods())()
        series = {'series_id': 42, 'name': 'Show', 'favorite': True}
        other = {'series_id': 43, 'name': 'Other', 'favorite': True}
        streams = QtWidgets.QListWidget()
        for entry in (series, other):
            streams.addItem(entry['name'])
            streams.item(streams.count() - 1).setData(Qt.UserRole, entry)
        streams.setCurrentRow(0)
        harness.streaming_list_widgets = {'Series': streams}
        harness.series_navigation_level = 0
        harness.entries_per_stream_type = {'Series': [series, other]}
        harness.currently_loaded_streams = {'Series': [series, other]}
        harness.category_view_cache = {'Series': {}}
        harness.category_item_cache = {'Series': {}}
        harness.active_category_view_key = {'Series': None}
        harness.fav_categories_text = 'Favorites'
        harness._selected_category = Mock(return_value=('Favorites', None))
        harness._category_view_key = Mock(return_value=('favorites', False, 0))
        harness.favorites_file = 'unused.json'
        harness._refresh_category_count_labels = Mock()
        harness.animate_progress = Mock()
        harness.favorite_button_pressed('Series', Mock())
        self.assertEqual(streams.count(), 1)
        self.assertEqual(streams.item(0).data(Qt.UserRole)['series_id'], 43)
        self.assertEqual(harness.currently_loaded_streams['Series'], [other])
        harness.animate_progress.assert_not_called()
