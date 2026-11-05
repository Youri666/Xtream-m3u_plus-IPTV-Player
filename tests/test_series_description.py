"""Episode selection and series navigation share the player's synopsis rules."""
import ast
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock
from PyQt5.QtCore import Qt
from iptv_player.programme_info import episode_summary


def description_methods():
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'IPTVPlayerApp')
    names = {'_update_series_description', 'streaming_item_clicked'}
    namespace = {'Qt': Qt, 'episode_summary': episode_summary, 'time': time}
    exec(compile(ast.Module(body=[node for node in cls.body if isinstance(node, ast.FunctionDef)
                                 and node.name in names], type_ignores=[]), str(source), 'exec'), namespace)
    return {name: namespace[name] for name in names}


class SeriesDescriptionTests(unittest.TestCase):
    def window(self, episode=None):
        window = type('Harness', (), description_methods())()
        window._catalog_installing = False
        window._series_back_click_guard_until = 0
        window.series_navigation_level = 2
        window.go_back_text = 'Go back'
        window.prev_clicked_streaming_item = None
        window.series_info_box = SimpleNamespace(_series_synopsis='Series synopsis', description=Mock())
        item = Mock()
        item.text.return_value = 'Episode title'
        item.data.return_value = episode
        window.streaming_list_widgets = {'Series': SimpleNamespace(currentItem=lambda: item)}
        window.tab_widget = SimpleNamespace(currentIndex=lambda: 0, tabText=lambda index: 'Series')
        return window, item

    def test_single_click_uses_episode_description_even_without_stream_type(self):
        window, item = self.window({'url': 'private://episode', 'info': {'plot': 'Episode synopsis'}})
        window.streaming_item_clicked(item)
        window.series_info_box.description.setText.assert_called_once_with('Episode synopsis')

    def test_missing_episode_synopsis_restores_series_instead_of_previous_episode(self):
        window, _item = self.window({'url': 'private://episode', 'info': {}})
        window._update_series_description()
        window.series_info_box.description.setText.assert_called_once_with('Series synopsis')

    def test_return_to_seasons_restores_series_description(self):
        window, _item = self.window({'info': {'plot': 'Episode synopsis'}})
        window._update_series_description()
        window.series_navigation_level = 1
        window._update_series_description()
        self.assertEqual(window.series_info_box.description.setText.call_args.args[0], 'Series synopsis')

    def test_late_series_enrichment_cannot_replace_selected_episode_synopsis(self):
        window, _item = self.window({'info': {'description': 'Episode synopsis'}})
        window.series_info_box._series_synopsis = 'Enriched series synopsis'
        window._update_series_description()
        window.series_info_box.description.setText.assert_called_once_with('Episode synopsis')

    def test_malformed_episode_info_has_no_synopsis(self):
        self.assertEqual(episode_summary({'info': 'invalid'}), '')
        self.assertEqual(episode_summary(None), '')
