"""Verify rating sorting persists per category and rebuilds from provider order."""

import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from iptv_player.config.preferences import CONTENT_TYPES
from iptv_player.storage.provider_preferences import load_provider_preferences, save_provider_preferences
from iptv_player.utils.sorting import ordered_catalog_entries


def rating_methods():
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'IPTVPlayerApp')
    names = {'_sorting_preference_value', '_sorting_tuple_from_preference',
             '_category_sort_preference_key', '_sorting_for_category',
             '_load_category_sort_preferences', '_load_account_sort_preferences',
             '_save_category_sort_preferences', '_category_view_key', '_entries_for_category_view'}
    namespace = dict(CONTENT_TYPES=CONTENT_TYPES, load_provider_preferences=load_provider_preferences,
                     save_provider_preferences=save_provider_preferences,
                     ordered_catalog_entries=ordered_catalog_entries)
    module = ast.Module(body=[n for n in cls.body if isinstance(n, ast.FunctionDef)
                             and n.name in names], type_ignores=[])
    exec(compile(module, str(source), 'exec'), namespace)
    return {name: namespace[name] for name in names}


class RatingPreferenceTests(unittest.TestCase):
    def harness(self, filename):
        harness = type('RatingHarness', (), rating_methods())()
        harness.provider_preferences_file = str(filename)
        harness.sorting_enabled = False
        harness.sorting_order = 0
        harness.remember_category_sorting = True
        harness.all_categories_text = 'All'
        harness.fav_categories_text = 'Favorites'
        harness.category_view_cache = {tab: {} for tab in CONTENT_TYPES}
        harness._load_account_sort_preferences()
        return harness

    def test_saved_rating_choices_survive_reload_and_category_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'provider.json'
            original = self.harness(filename)
            original.category_sort_preferences['Movies']['category:1'] = 'rating_desc'
            original.category_sort_preferences['Series']['category:2'] = 'rating_asc'
            original._save_category_sort_preferences()
            restored = self.harness(filename)
            self.assertEqual(restored._sorting_for_category('Movies', 'Films', 1), (True, 2))
            self.assertEqual(restored._sorting_for_category('Series', 'Shows', 2), (True, 3))
            self.assertEqual(restored._sorting_for_category('Movies', 'Other', 3), (False, 0))
            self.assertEqual(restored._sorting_preference_value(True, 2), 'rating_desc')
            self.assertEqual(restored._sorting_preference_value(True, 3), 'rating_asc')
            entries = [{'name': 'Zulu', 'rating': 8}, {'name': 'Alpha', 'rating': 8},
                       {'name': 'High', 'rating': 9}, {'name': 'None'}]
            restored._raw_entries_for_category = Mock(return_value=entries)
            ordered = restored._entries_for_category_view('Movies', 'Films', 1)
            self.assertEqual([e['name'] for e in ordered], ['High', 'Zulu', 'Alpha', 'None'])
            restored.category_sort_preferences['Movies']['category:1'] = 'rating_asc'
            ordered = restored._entries_for_category_view('Movies', 'Films', 1)
            self.assertEqual([e['name'] for e in ordered], ['Zulu', 'Alpha', 'High', 'None'])
