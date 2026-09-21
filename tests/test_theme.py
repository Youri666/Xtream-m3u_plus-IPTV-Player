"""Regression coverage for returning from forced themes to desktop preferences."""

import os
import subprocess
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor
from iptv_player.ui.theme import apply_application_theme, application_palette_is_dark


class MacSystemThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.palette = self.app.palette()

    def tearDown(self):
        self.app.setPalette(self.palette)

    @patch('iptv_player.ui.theme.sys.platform', 'darwin')
    @patch('iptv_player.ui.theme.subprocess.run')
    def test_system_rereads_preference_after_forced_theme(self, run):
        apply_application_theme(self.app, 'Dark')
        self.assertTrue(application_palette_is_dark(self.app))
        run.return_value = subprocess.CompletedProcess([], 1, '', 'missing key')
        self.assertFalse(apply_application_theme(self.app, 'System'))
        self.assertFalse(application_palette_is_dark(self.app))

        apply_application_theme(self.app, 'Light')
        run.return_value = subprocess.CompletedProcess([], 0, 'Dark\n', '')
        self.assertTrue(apply_application_theme(self.app, 'System'))
        self.assertTrue(application_palette_is_dark(self.app))
        self.assertEqual(run.call_count, 2)

    @patch('iptv_player.ui.theme.sys.platform', 'darwin')
    @patch('iptv_player.ui.theme.subprocess.run')
    def test_failed_system_query_does_not_reuse_forced_dark(self, run):
        for error in (OSError('unavailable'), subprocess.TimeoutExpired('defaults', 2)):
            with self.subTest(error=type(error).__name__):
                apply_application_theme(self.app, 'Dark')
                run.side_effect = error
                self.assertFalse(apply_application_theme(self.app, 'System'))


@patch('iptv_player.ui.theme.sys.platform', 'linux')
class LinuxSystemThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.palette = self.app.palette()
        self.saved_native = getattr(self.app, '_iptv_system_palette', None)
        native = QPalette()
        native.setColor(QPalette.Window, QColor('white'))
        self.app._iptv_system_palette = native

    def tearDown(self):
        self.app.setPalette(self.palette)
        if self.saved_native is None:
            del self.app._iptv_system_palette
        else:
            self.app._iptv_system_palette = self.saved_native

    @patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'GNOME'})
    @patch('iptv_player.ui.theme.subprocess.run')
    def test_modern_gnome_rereads_explicit_preference(self, run):
        for value, expected in [('prefer-light', False), ('prefer-dark', True)]:
            apply_application_theme(self.app, 'Dark' if not expected else 'Light')
            run.return_value = subprocess.CompletedProcess([], 0, repr(value), '')
            self.assertEqual(apply_application_theme(self.app, 'System'), expected)
            self.assertEqual(application_palette_is_dark(self.app), expected)
        self.assertEqual(run.call_count, 2)

    @patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'GNOME-Classic:GNOME'})
    @patch('iptv_player.ui.theme.subprocess.run')
    def test_legacy_gnome_uses_gtk_theme(self, run):
        for code, scheme in [(1, ''), (0, "'default'")]:
            for theme, expected in [('Adwaita', False), ('Adwaita-dark', True)]:
                run.side_effect = [
                    subprocess.CompletedProcess([], code, scheme, ''),
                    subprocess.CompletedProcess([], 0, repr(theme), ''),
                ]
                apply_application_theme(self.app, 'Dark' if not expected else 'Light')
                self.assertEqual(apply_application_theme(self.app, 'System'), expected)

    @patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'GNOME'})
    @patch('iptv_player.ui.theme.subprocess.run', side_effect=FileNotFoundError)
    def test_missing_gsettings_uses_unmodified_native_palette(self, run):
        apply_application_theme(self.app, 'Dark')
        self.assertFalse(apply_application_theme(self.app, 'System'))

    @patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE', 'DESKTOP_SESSION': 'plasma'})
    @patch('iptv_player.ui.theme.subprocess.run')
    def test_other_desktop_does_not_consult_unrelated_gnome_settings(self, run):
        self.app._iptv_system_palette.setColor(QPalette.Window, QColor('black'))
        apply_application_theme(self.app, 'Light')
        self.assertTrue(apply_application_theme(self.app, 'System'))
        run.assert_not_called()
