"""Verify auxiliary tab visibility without disabling History or catalogue data."""

import ast
from datetime import datetime
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QWidget, QTabWidget, QCheckBox, QComboBox

from iptv_player.config.preferences import CONTENT_TYPES, load_content_preferences, remove_content_preferences
from iptv_player.storage.provider_preferences import load_provider_preferences, save_provider_preferences
from iptv_player.storage.history import load_history, record_history, resume_position


def visibility_methods():
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'IPTVPlayerApp')
    names = {'_apply_content_visibility', 'toggle_tab_visibility', '_sync_tab_visibility_checkboxes',
             '_load_account_content_preferences', '_tab_widgets_by_key', '_available_default_tabs',
             '_refresh_default_tab_options', '_select_tab_with_history_fallback',
             '_is_info_tab_visible', '_update_account_info_timer', '_record_history_access',
             '_history_with_saved_progress'}
    namespace = dict(CONTENT_TYPES=CONTENT_TYPES, LAST_SELECTED_TAB='Last selected tab',
                     load_provider_preferences=load_provider_preferences,
                     save_provider_preferences=save_provider_preferences,
                     load_content_preferences=load_content_preferences,
                     remove_content_preferences=remove_content_preferences,
                     datetime=datetime, logging=logging, load_history=load_history, record_history=record_history)
    module = ast.Module(body=[n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names],
                        type_ignores=[])
    exec(compile(module, str(source), 'exec'), namespace)
    return {name: namespace[name] for name in names}


class TabVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.h = type('VisibilityHarness', (), visibility_methods())()
        h = self.h
        h.user_data_file = str(Path(self.directory.name) / 'userdata.ini')
        h.provider_preferences_file = str(Path(self.directory.name) / 'account-a.json')
        h.tab_widget = QTabWidget()
        self.addCleanup(h.tab_widget.close)
        h.content_tabs = {key: QWidget() for key in CONTENT_TYPES}
        h.history_tab, h.info_tab, h.settings_tab = QWidget(), QWidget(), QWidget()
        for key, tab in h._tab_widgets_by_key().items():
            h.tab_widget.addTab(tab, key)
        h.content_enabled = {key: True for key in CONTENT_TYPES}
        h.tab_visibility = {'History': True, 'Info': True}
        h.content_checkboxes = {key: QCheckBox() for key in CONTENT_TYPES}
        h.tab_visibility_checkboxes = {key: QCheckBox() for key in h.tab_visibility}
        h.default_tab_selector = QComboBox()
        h.default_tab_key = 'History'
        h._restoring_tab_preferences = False
        h._save_account_tab_preferences = Mock()
        h.fetch_data_thread = Mock()
        h.account_info_timer = Mock()
        h.account_info_auto_refresh_enabled = True
        h.account_info_refresh_interval = 60
        h.server, h.username, h.password = 'server', 'user', 'password'
        h.history_file = str(Path(self.directory.name) / 'history.json')
        h.history_size = 50
        h.refresh_history_tab = Mock()
        save_provider_preferences(h.provider_preferences_file, {}, {}, h.content_enabled)

    def test_hidden_tabs_leave_settings_and_default_choices_available(self):
        h = self.h
        h.tab_widget.setCurrentWidget(h.history_tab)
        h.toggle_tab_visibility('History', False)
        h.toggle_tab_visibility('Info', False)
        self.assertNotIn('History', h._available_default_tabs())
        self.assertNotIn('Info', h._available_default_tabs())
        self.assertIn('Settings', h._available_default_tabs())
        self.assertIn(h.default_tab_key, h._available_default_tabs())
        self.assertNotEqual(h.tab_widget.currentWidget(), h.history_tab)
        self.assertEqual(h.content_enabled, {key: True for key in CONTENT_TYPES})
        h.fetch_data_thread.assert_not_called()
        h.toggle_tab_visibility('History', True)
        self.assertIn('History', h._available_default_tabs())
        h.fetch_data_thread.assert_not_called()

    def test_only_settings_remains_and_hidden_last_tab_falls_back(self):
        h = self.h
        h.content_enabled = {key: False for key in CONTENT_TYPES}
        h.toggle_tab_visibility('History', False)
        h.toggle_tab_visibility('Info', False)
        self.assertEqual(h._available_default_tabs(), ['Settings'])
        self.assertEqual(h.default_tab_key, 'Settings')
        h._select_tab_with_history_fallback('Info')
        self.assertIs(h.tab_widget.currentWidget(), h.settings_tab)

    def test_restores_account_choices_and_other_accounts_default_to_visible(self):
        h = self.h
        h.toggle_tab_visibility('History', False)
        h.toggle_tab_visibility('Info', False)
        h.tab_visibility = {'History': True, 'Info': True}
        h._load_account_content_preferences()
        self.assertEqual(h.tab_visibility, {'History': False, 'Info': False})
        self.assertFalse(h.tab_visibility_checkboxes['History'].isChecked())
        h.provider_preferences_file = str(Path(self.directory.name) / 'account-b.json')
        save_provider_preferences(h.provider_preferences_file, {}, {}, h.content_enabled)
        h._load_account_content_preferences()
        self.assertEqual(h.tab_visibility, {'History': True, 'Info': True})
        self.assertTrue(h.tab_visibility_checkboxes['History'].isChecked())
        self.assertIn('History', h._available_default_tabs())

    def test_hidden_history_still_records_and_preserves_resume_position(self):
        h = self.h
        entry = {'key': 'Series:42', 'type': 'Series', 'stream_id': 42,
                 'title': 'Episode', 'position_ms': 12345, 'duration_ms': 90000}
        record_history(h.history_file, entry, h.history_size)
        h.toggle_tab_visibility('History', False)
        current = dict(entry)
        current.pop('position_ms')
        h._record_history_access(current)
        entries = load_history(h.history_file)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['position_ms'], 12345)
        self.assertEqual(resume_position(entries[0]), 12345)

    def test_hiding_info_stops_its_refresh_timer(self):
        h = self.h
        h.tab_widget.setCurrentWidget(h.info_tab)
        h._update_account_info_timer()
        h.account_info_timer.start.assert_called_once_with(60000)
        h.toggle_tab_visibility('Info', False)
        self.assertFalse(h._is_info_tab_visible())
        h.account_info_timer.stop.assert_called()
