import unittest
from unittest.mock import patch

from PyQt5 import QtCore, QtGui

from iptv_player.bootstrap import configure_qt_high_dpi


class HighDpiConfigurationTests(unittest.TestCase):
    def test_enables_scaling_and_high_resolution_pixmaps(self):
        with patch.object(
            QtCore.QCoreApplication, "setAttribute"
        ) as set_attribute, patch.object(
            QtGui.QGuiApplication, "setHighDpiScaleFactorRoundingPolicy"
        ) as set_rounding_policy:
            configure_qt_high_dpi()

        requested_attributes = {
            call.args[0] for call in set_attribute.call_args_list
        }
        self.assertIn(QtCore.Qt.AA_EnableHighDpiScaling, requested_attributes)
        self.assertIn(QtCore.Qt.AA_UseHighDpiPixmaps, requested_attributes)
        set_rounding_policy.assert_called_once_with(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )


if __name__ == "__main__":
    unittest.main()
