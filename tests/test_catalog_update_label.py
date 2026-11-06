"""The Info date reflects actual successful catalogue fetches per account."""
import ast
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import Mock
from iptv_player.provider.catalog_refresh import CatalogRefreshPolicy, catalog_last_updated_text


def label_methods():
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    cls = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(node, ast.ClassDef) and node.name == 'IPTVPlayerApp')
    names = {'_update_catalog_refresh_button', '_finish_catalog_refresh'}
    namespace = {'catalog_last_updated_text': catalog_last_updated_text}
    exec(compile(ast.Module(body=[node for node in cls.body if isinstance(node, ast.FunctionDef)
                                 and node.name in names], type_ignores=[]), str(source), 'exec'), namespace)
    return {name: namespace[name] for name in names}


class CatalogUpdateLabelTests(unittest.TestCase):
    def window(self):
        window = type('Harness', (), label_methods())()
        window._catalog_refresh_policy = CatalogRefreshPolicy()
        window.active_account_id = 'A'
        window.refresh_catalog_button = Mock()
        window.catalog_last_refresh_label = Mock()
        window._catalog_reload_pending = set()
        return window

    def test_completed_refresh_and_cache_load_show_original_fetch_time(self):
        window = self.window()
        fetched_at = 1700000000
        window._finish_catalog_refresh('A', True, fetched_at)
        expected = 'Catalog last updated: ' + datetime.fromtimestamp(fetched_at).strftime('%Y-%m-%d %H:%M:%S')
        window.catalog_last_refresh_label.setText.assert_called_with(expected)
        window._finish_catalog_refresh('A', True, fetched_at)
        window.catalog_last_refresh_label.setText.assert_called_with(expected)

    def test_failed_refresh_retains_previous_success_date(self):
        window = self.window()
        window._finish_catalog_refresh('A', True, 1700000000)
        window._finish_catalog_refresh('A', False)
        window.catalog_last_refresh_label.setText.assert_called_with(catalog_last_updated_text(1700000000))

    def test_account_switch_and_background_completion_cannot_mix_dates(self):
        window = self.window()
        window._finish_catalog_refresh('A', True, 1700000000)
        window.active_account_id = 'B'
        window._update_catalog_refresh_button()
        window.catalog_last_refresh_label.setText.assert_called_with(catalog_last_updated_text(None))
        window._finish_catalog_refresh('A', True, 1700100000)
        window.catalog_last_refresh_label.setText.assert_called_with(catalog_last_updated_text(None))
        window._finish_catalog_refresh('B', True, 1700200000)
        window.catalog_last_refresh_label.setText.assert_called_with(catalog_last_updated_text(1700200000))

    def test_missing_or_invalid_timestamp_is_explicit(self):
        for value in (None, '', 0, -1, 'invalid', float('nan'), float('inf')):
            with self.subTest(value=value):
                self.assertEqual(catalog_last_updated_text(value), 'Catalog last updated: Not available')
