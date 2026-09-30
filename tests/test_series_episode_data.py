"""Provider episode shapes and graceful GUI failure regression tests."""

import ast
import logging
from pathlib import Path
import unittest
from unittest.mock import Mock

from iptv_player.provider.series import episodes_by_season


class SeriesEpisodeDataTests(unittest.TestCase):
    def test_existing_mapping_preserves_episode_order(self):
        rows = [{'id': 2}, {'id': 1}]
        self.assertEqual(episodes_by_season({'1': rows}), {'1': rows})

    def test_flat_list_groups_explicit_seasons_including_specials(self):
        rows = [{'id': 1, 'season': 0}, {'id': 2, 'season': '1'},
                {'id': 3, 'season': 1}]
        self.assertEqual(episodes_by_season(rows), {'0': rows[:1], '1': rows[1:]})

    def test_empty_list_is_an_empty_collection(self):
        self.assertEqual(episodes_by_season([]), {})

    def test_invalid_data_does_not_invent_a_season(self):
        for value in (None, 'invalid', [{'id': 1}], [['episode']], {'1': None}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                episodes_by_season(value)

    def test_gui_finishes_loading_without_replacing_list_on_invalid_or_empty_data(self):
        source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == 'IPTVPlayerApp')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'process_series_info')
        namespace = {'episodes_by_season': episodes_by_season, 'logging': logging}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
        for episodes, expected in (([], 'No episodes available'),
                                   ([{'id': 1, 'season': 1}, {'id': 2}], 'Invalid series episode data')):
            with self.subTest(episodes=episodes):
                harness = type('Harness', (), {'process_series_info': namespace['process_series_info']})()
                harness._is_current_info_request = Mock(return_value=True)
                harness.animate_progress = Mock()
                harness.go_back_to_level = Mock()
                harness.process_series_info({'episodes': episodes}, True)
                harness.animate_progress.assert_called_once_with(0, 100, expected, 'error')
                harness.go_back_to_level.assert_called_once_with(0)
                self.assertEqual(harness.series_navigation_level, 0)

    def test_nested_season_lists_use_explicit_seasons_not_array_positions(self):
        special = {'id': 1, 'season': 0}
        first = {'id': 2, 'season': 1}
        last = {'id': 3, 'season': 23}
        data = [[special], [first], [], [last]]
        self.assertEqual(episodes_by_season(data),
                         {'0': [special], '1': [first], '23': [last]})

    def test_nested_lists_without_season_metadata_are_rejected(self):
        with self.assertRaises(ValueError):
            episodes_by_season([[{'id': 1}]])
