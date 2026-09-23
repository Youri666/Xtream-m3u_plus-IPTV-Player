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
             'set_progress_state', 'set_progress_text', 'favorite_button_pressed',
             '_next_info_request_generation', '_is_current_info_request',
             '_reset_info_panel', '_current_favorite_state'}
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

    def test_reset_invalidates_pending_information_results(self):
        harness = type('CatalogHarness', (), catalog_methods())()
        streams = QtWidgets.QListWidget()
        streams.addItem("Old movie")
        streams.setCurrentRow(0)
        panel = Mock()
        harness._info_request_generation = {
            'LIVE': 0, 'Movies': 4, 'Series': 0,
        }
        harness.streaming_list_widgets = {'Movies': streams}
        harness.info_boxes = {'Movies': panel}

        harness._reset_info_panel('Movies')

        self.assertFalse(harness._is_current_info_request('Movies', 4))
        self.assertTrue(harness._is_current_info_request('Movies', 5))
        self.assertIsNone(streams.currentItem())
        panel.reset.assert_called_once_with()

    def test_cached_row_uses_current_catalog_favorite_state(self):
        harness = type('CatalogHarness', (), catalog_methods())()
        harness.entries_per_stream_type = {
            'LIVE': [{'stream_id': 42, 'favorite': False}],
        }
        cached_row = {'stream_id': 42, 'favorite': True}

        self.assertFalse(harness._current_favorite_state('LIVE', cached_row))

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
                harness.streaming_item_clicked = Mock()
                harness._reset_info_panel = Mock()
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
        harness.streaming_item_clicked = Mock()
        harness._reset_info_panel = Mock()
        harness.favorite_button_pressed('Series', Mock())
        self.assertEqual(streams.count(), 1)
        self.assertEqual(streams.item(0).data(Qt.UserRole)['series_id'], 43)
        self.assertEqual(harness.currently_loaded_streams['Series'], [other])
        self.assertIs(streams.currentItem(), streams.item(0))
        harness.streaming_item_clicked.assert_called_once_with(streams.item(0))
        harness._reset_info_panel.assert_not_called()
        harness.animate_progress.assert_not_called()

    def test_removing_last_favorite_clears_information_panel(self):
        harness = type('CatalogHarness', (), catalog_methods())()
        movie = {'stream_id': 42, 'name': 'Movie', 'favorite': True}
        streams = QtWidgets.QListWidget()
        streams.addItem(movie['name'])
        streams.item(0).setData(Qt.UserRole, movie)
        streams.setCurrentRow(0)
        harness.streaming_list_widgets = {'Movies': streams}
        harness.entries_per_stream_type = {'Movies': [movie]}
        harness.currently_loaded_streams = {'Movies': [movie]}
        harness.category_view_cache = {'Movies': {}}
        harness.category_item_cache = {'Movies': {}}
        harness.active_category_view_key = {'Movies': None}
        harness.fav_categories_text = 'Favorites'
        harness._selected_category = Mock(return_value=('Favorites', None))
        harness._category_view_key = Mock(return_value=('favorites', False, 0))
        harness.favorites_file = 'unused.json'
        harness._refresh_category_count_labels = Mock()
        harness.animate_progress = Mock()
        harness.streaming_item_clicked = Mock()
        harness._reset_info_panel = Mock()

        harness.favorite_button_pressed('Movies', Mock())

        self.assertEqual(streams.count(), 1)
        self.assertEqual(streams.item(0).text(), 'No items in list...')
        harness._reset_info_panel.assert_called_once_with('Movies')
        harness.streaming_item_clicked.assert_not_called()
