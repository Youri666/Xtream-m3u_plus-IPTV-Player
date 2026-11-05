"""Follow playback in the main Series view without playback or tab activation."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QListWidget, QListWidgetItem


def sync_methods():
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    cls = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(node, ast.ClassDef) and node.name == 'IPTVPlayerApp')
    names = {'_select_series_episode', '_sync_series_playback'}
    namespace = {'Qt': Qt}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node for node in cls.body
         if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])), 'sync', 'exec'), namespace)
    return {name: namespace[name] for name in names}


class SeriesPlaybackSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def harness(self):
        window = type('SeriesSyncHarness', (), sync_methods())()
        window.active_account_id = 'A'
        window._catalog_loaded = True
        window._catalog_installing = False
        window._pending_history_series = None
        window.content_enabled = {'Series': True}
        window.current_series_entry = {'series_id': '10'}
        window.current_series_season = '1'
        window.series_navigation_level = 2
        window.currently_loaded_streams = {'Seasons': {'1': [{'id': '1'}, {'id': '2'}], '2': [{'id': '3'}]}}
        window._selected_category = lambda kind: ('Favorites', None)
        window.streaming_list_widgets = {'Series': QListWidget()}
        window._next_info_request_generation = Mock()
        window._scroll_to_catalog_item = Mock()
        window.streaming_item_clicked = Mock()
        window._open_history_series = Mock(return_value=True)
        window.tab_widget = Mock()
        window.play_item = Mock()
        def show(episodes):
            widget = window.streaming_list_widgets['Series']
            widget.clear()
            for episode in episodes:
                item = QListWidgetItem('Episode ' + episode['id'])
                item.setData(Qt.UserRole, episode)
                widget.addItem(item)
        window.show_episodes = Mock(side_effect=show)
        show(window.currently_loaded_streams['Seasons']['1'])
        return window

    def entry(self, stream='2', season='1', account='A'):
        return dict(type='Series', account_id=account, series_id='10', stream_id=stream,
                    season=season, source_category_name='Favorites', source_category_id='')

    def test_next_episode_follows_favorites_without_rebuilding_or_changing_tab(self):
        window = self.harness()
        window._sync_series_playback(self.entry())
        selected = window.streaming_list_widgets['Series'].currentItem()
        self.assertEqual(selected.data(Qt.UserRole)['id'], '2')
        window.show_episodes.assert_not_called()
        window._open_history_series.assert_not_called()
        window.tab_widget.setCurrentWidget.assert_not_called()
        window.play_item.assert_not_called()
        window._sync_series_playback(self.entry())
        self.assertEqual(window.streaming_item_clicked.call_count, 1)

    def test_new_season_is_opened_and_selected(self):
        window = self.harness()
        window._sync_series_playback(self.entry('3', '2'))
        self.assertEqual(window.current_series_season, '2')
        self.assertEqual(window.series_navigation_level, 2)
        self.assertEqual(window.streaming_list_widgets['Series'].currentItem().data(Qt.UserRole)['id'], '3')
        window.show_episodes.assert_called_once()
        window.play_item.assert_not_called()
        window.tab_widget.setCurrentWidget.assert_not_called()

    def test_other_account_does_not_change_selection(self):
        window = self.harness()
        window._sync_series_playback(self.entry(account='B'))
        window.streaming_item_clicked.assert_not_called()
        window._open_history_series.assert_not_called()

    def test_different_origin_reuses_history_navigation_without_switching_tabs(self):
        window = self.harness()
        window._selected_category = lambda kind: ('All', None)
        entry = self.entry()
        window._sync_series_playback(entry)
        window._open_history_series.assert_called_once_with(dict(entry, _playback_sync=True), switch_tab=False)

    def test_loading_catalogue_defers_selection(self):
        window = self.harness()
        window._catalog_loaded = False
        window._sync_series_playback(self.entry())
        self.assertEqual(window._pending_playback_selection, self.entry())
        window.streaming_item_clicked.assert_not_called()
        window._open_history_series.assert_not_called()
        window._catalog_loaded = True
        window._sync_series_playback(window._pending_playback_selection)
        self.assertEqual(window.streaming_list_widgets['Series'].currentItem().data(Qt.UserRole)['id'], '2')

    def test_loading_same_episode_does_not_queue_duplicate_series_requests(self):
        window = self.harness()
        window._selected_category = lambda kind: ('All', None)
        window._pending_history_series = dict(self.entry(), _playback_sync=True)
        window._sync_series_playback(self.entry())
        window._open_history_series.assert_not_called()

    def test_event_batch_follows_only_the_latest_episode_without_writing_fake_progress(self):
        import queue
        source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
        cls = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                   if isinstance(node, ast.ClassDef) and node.name == 'IPTVPlayerApp')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_process_embedded_player_events')
        namespace = dict(queue=queue, record_history=Mock())
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), 'events', 'exec'), namespace)
        window = SimpleNamespace(active_account_id='A', _embedded_player_event_queue=queue.Queue(),
                                 _sync_series_playback=Mock(), refresh_history_tab=Mock())
        window._embedded_player_event_queue.put({'event': 'playback_started', 'history': self.entry('1')})
        window._embedded_player_event_queue.put({'event': 'playback_started', 'history': self.entry('2')})
        namespace['_process_embedded_player_events'](window)
        window._sync_series_playback.assert_called_once_with(self.entry('2'))
        namespace['record_history'].assert_not_called()

    def test_newer_episode_invalidates_previous_pending_navigation(self):
        window = self.harness()
        window._pending_history_series = dict(self.entry('1'), _playback_sync=True)
        window._sync_series_playback(self.entry('2'))
        window._next_info_request_generation.assert_called_once_with('Series')
        self.assertIsNone(window._pending_history_series)
        self.assertEqual(window.streaming_list_widgets['Series'].currentItem().data(Qt.UserRole)['id'], '2')
