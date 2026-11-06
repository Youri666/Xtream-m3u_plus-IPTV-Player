"""Toolbar shortcuts invoke the same actions as mouse clicks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QShortcut
import test_programme_panel as panels


class PlayerToolbarShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        panels.ProgrammePanelTests.setUpClass()
        cls.app = panels.ProgrammePanelTests.app

    def window(self, filename):
        window = panels.ProgrammePanelTests().window(filename)
        window.activateWindow()
        self.app.processEvents()
        return window

    def test_programme_shortcut_toggles_panel_and_respects_disabled_button(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window.btn_programme.setEnabled(False)
            QTest.keyClick(window, Qt.Key_P)
            window._progress_callback.assert_not_called()
            window.btn_programme.setEnabled(True)
            QTest.keyClick(window, Qt.Key_P)
            self.assertTrue(window.btn_programme.isChecked())
            self.assertEqual(window._progress_callback.call_args.args[0]['event'], 'programme_request')
            QTest.keyClick(window, Qt.Key_P)
            self.assertFalse(window.btn_programme.isChecked())
            self.assertIn('(P)', window.btn_programme.toolTip())
            window.close()

    def test_ratio_shortcut_cycles_formats_and_click_opens_checked_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            self.assertIsNone(window.btn_format.menu())
            with patch.object(window.format_menu, 'exec_') as show_menu:
                QTest.keyClick(window, Qt.Key_R)
                self.assertEqual(window._video_format, '16:9')
                self.assertTrue(window.format_actions['16:9'].isChecked())
                self.assertIn('16:9', window.track_osd.text())
                show_menu.assert_not_called()
                window.btn_format.click()
                show_menu.assert_called_once()
            for _ in range(len(window.format_actions) - 1):
                QTest.keyClick(window, Qt.Key_R)
            self.assertEqual(window._video_format, 'Auto')
            shortcuts = {shortcut.key().toString(): shortcut for shortcut in window.findChildren(QShortcut)}
            for key in ('P', 'R', 'K'):
                self.assertFalse(shortcuts[key].autoRepeat())
            self.assertIn('R cycles formats', window.btn_format.toolTip())
            window.close()

    def test_lock_shortcut_persists_choice_and_is_inactive_in_fullscreen(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            before = window._window_aspect_locked
            QTest.keyClick(window, Qt.Key_K)
            self.assertEqual(window._window_aspect_locked, not before)
            window.toggle_fullscreen()
            window.activateWindow()
            self.app.processEvents()
            QTest.keyClick(window, Qt.Key_K)
            self.assertEqual(window._window_aspect_locked, not before)
            self.assertIn('(K)', window.btn_aspect_lock.toolTip())
            window.toggle_fullscreen()
            window.close()

    def test_ratio_choices_use_checkboxes_with_exactly_one_active_format(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            self.assertTrue(all(action.actionGroup() is None
                                for action in window.format_actions.values()))
            window.format_actions['4:3'].trigger()
            self.assertEqual([name for name, action in window.format_actions.items()
                              if action.isChecked()], ['4:3'])
            # Clicking the current choice must not leave every box unchecked.
            window.format_actions['4:3'].trigger()
            self.assertTrue(window.format_actions['4:3'].isChecked())
            window.player.video_set_aspect_ratio.side_effect = ValueError('Unavailable')
            with self.assertLogs(level='WARNING'):
                window.format_actions['16:9'].trigger()
            self.assertEqual(window._video_format, '4:3')
            self.assertEqual([name for name, action in window.format_actions.items()
                              if action.isChecked()], ['4:3'])
            window.close()
