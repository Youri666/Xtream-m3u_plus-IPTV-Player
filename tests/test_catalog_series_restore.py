"""A catalogue refresh restores series details as well as the episode list."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QListWidget, QListWidgetItem, QLineEdit
from iptv_player.ui.catalog_state import capture_catalog_view, restore_catalog_view


class CatalogSeriesRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self):
        category, streams = QListWidget(), QListWidget()
        category_item = QListWidgetItem('Favorites')
        category_item.setData(Qt.UserRole, {'category_id': 'favorites'})
        category.addItem(category_item)
        category.setCurrentItem(category_item)
        back = QListWidgetItem('Go back')
        streams.addItem(back)
        episode = QListWidgetItem('Episode 13')
        episode.setData(Qt.UserRole, {'id': '13', 'info': {'plot': 'Episode synopsis'}})
        streams.addItem(episode)
        streams.setCurrentItem(episode)
        window = SimpleNamespace(category_list_widgets={'Series': category},
            streaming_list_widgets={'Series': streams},
            category_search_bars={'Series': QLineEdit()}, streaming_search_bars={'Series': QLineEdit()},
            series_navigation_level=2, current_series_entry={'series_id': '10'}, current_series_season='2',
            currently_loaded_streams={'Seasons': {'2': [{'id': '13'}]}, 'Episodes': [{'id': '13'}]},
            entries_per_stream_type={'Series': [{'series_id': '10'}]}, content_enabled={'Series': True},
            _next_info_request_generation=Mock(return_value=7), fetch_series_info=Mock())
        return window

    def test_series_details_reload_without_replacing_the_restored_episode_selection(self):
        window = self.window()
        saved = capture_catalog_view(window)
        window.streaming_list_widgets['Series'].clear()
        window.series_navigation_level = 0
        restore_catalog_view(window, saved)
        self.assertEqual(window.series_navigation_level, 2)
        self.assertEqual(window.current_series_season, '2')
        self.assertEqual(window.streaming_list_widgets['Series'].currentItem().data(Qt.UserRole)['id'], '13')
        window.fetch_series_info.assert_called_once_with('10', False, 7)

    def test_removed_series_does_not_reload_stale_details(self):
        window = self.window()
        saved = capture_catalog_view(window)
        window.entries_per_stream_type['Series'] = []
        window.streaming_list_widgets['Series'].clear()
        window.series_navigation_level = 0
        restore_catalog_view(window, saved)
        window.fetch_series_info.assert_not_called()
        self.assertEqual(window.series_navigation_level, 0)
