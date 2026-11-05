"""Manual and automatic refresh share exclusion, age checks and error backoff."""
import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from iptv_player.provider.catalog_refresh import CatalogRefreshPolicy
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QListWidget, QLineEdit


class CatalogRefreshTests(unittest.TestCase):
    def test_expiry_uses_original_fetch_time_and_prevents_overlap(self):
        policy = CatalogRefreshPolicy()
        policy.finish('A', True, 100)
        with patch('iptv_player.provider.catalog_refresh.time.time', return_value=3701):
            self.assertTrue(policy.due('A', 1))
            self.assertTrue(policy.begin('A'))
            self.assertFalse(policy.begin('A'))
            self.assertFalse(policy.due('A', 1))
            self.assertTrue(policy.begin('B'))
        policy.finish('B', True, 200)
        self.assertIn('A', policy.busy)

    def test_failed_refresh_backs_off_but_manual_retry_is_allowed(self):
        policy = CatalogRefreshPolicy()
        policy.finish('A', True, 100)
        with patch('iptv_player.provider.catalog_refresh.time.time', return_value=5000):
            policy.finish('A', False)
            self.assertFalse(policy.due('A', 1))
            self.assertTrue(policy.begin('A'))
            policy.finish('A', False)
        with patch('iptv_player.provider.catalog_refresh.time.time', return_value=5301):
            self.assertTrue(policy.due('A', 1))
        self.assertFalse(policy.due('unknown', 1))

    def test_installation_blocks_list_callbacks_and_restores_widgets_on_error(self):
        app = QApplication.instance() or QApplication([])
        source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
        cls = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n, ast.ClassDef) and n.name == 'IPTVPlayerApp')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'process_data')
        namespace = dict(capture_catalog_view=Mock(), restore_catalog_view=Mock())
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), 'catalog_install', 'exec'), namespace)
        harness = Mock()
        harness._catalog_loaded = False
        harness._current_catalog_signal.return_value = True
        categories, streams = QListWidget(), QListWidget()
        search = QLineEdit()
        harness.category_list_widgets = {'LIVE': categories}
        harness.streaming_list_widgets = {'LIVE': streams}
        harness.category_search_bars = {'LIVE': search}
        harness.streaming_search_bars = {}
        clicked = Mock()
        categories.itemSelectionChanged.connect(clicked)
        queued = []
        def install(*args):
            self.assertFalse(categories.isEnabled())
            self.assertTrue(categories.signalsBlocked())
            categories.addItem('complete row')
            categories.setCurrentRow(0)
            QTimer.singleShot(0, lambda: queued.append(streams.count()))
            streams.addItems(['one', 'two'])
            self.assertEqual(queued, [])
        harness._install_catalog_data.side_effect = install
        namespace['process_data'](harness, {}, {}, {})
        clicked.assert_not_called()
        app.processEvents()
        self.assertEqual(queued, [2])
        self.assertTrue(categories.isEnabled())
        self.assertFalse(categories.signalsBlocked())
        harness._install_catalog_data.side_effect = RuntimeError('test failure')
        with self.assertRaises(RuntimeError):
            namespace['process_data'](harness, {}, {}, {})
        self.assertTrue(categories.isEnabled())
        self.assertTrue(categories.updatesEnabled())
        self.assertFalse(categories.signalsBlocked())
        self.assertFalse(harness._catalog_installing)
