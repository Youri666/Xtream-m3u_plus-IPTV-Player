"""Regression coverage for rejecting a second main application."""

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from iptv_player.bootstrap import acquire_application_lock


class InstanceLockTests(unittest.TestCase):
    def test_rejects_second_instance_and_releases_lock(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            with patch('PyQt5.QtCore.QStandardPaths.writableLocation', return_value=directory), \
                    patch('PyQt5.QtWidgets.QMessageBox.exec_', return_value=0) as message:
                first = acquire_application_lock()
                self.assertIsNotNone(first)
                self.assertIsNone(acquire_application_lock())
                message.assert_called_once()
                first.unlock()
                third = acquire_application_lock()
                self.assertIsNotNone(third)
                third.unlock()
