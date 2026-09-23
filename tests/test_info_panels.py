import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

from iptv_player.ui.info_panels import LiveInfoBox, MovieInfoBox, SeriesInfoBox


class _PanelParent:
    path_to_no_img = ""
    path_to_unknown_status_icon = ""
    path_to_yt_img = ""
    path_to_tmdb_img = ""
    favorites_icon = QIcon()
    favorites_icon_colour = QIcon()

    @staticmethod
    def status_pixmap(_path, _size):
        return QPixmap(1, 1)

    @staticmethod
    def favorite_button_pressed(_stream_type, _panel):
        pass


class InfoPanelResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.parent = _PanelParent()

    def test_live_reset_clears_stale_selection(self):
        panel = LiveInfoBox(self.parent)
        panel.EPG_box_label.setText("Old channel")
        panel.live_EPG_info.addTopLevelItem(QtWidgets.QTreeWidgetItem(["Old EPG"]))
        panel.fav_button.setEnabled(True)

        panel.reset()

        self.assertEqual(
            panel.EPG_box_label.text(), "Select channel to view Live TV info"
        )
        self.assertEqual(panel.live_EPG_info.topLevelItemCount(), 0)
        self.assertFalse(panel.fav_button.isEnabled())

    def test_movie_reset_clears_stale_selection(self):
        panel = MovieInfoBox(self.parent)
        panel.name.setText("Old movie")
        panel.yt_code = "trailer"
        panel.fav_button.setEnabled(True)

        panel.reset()

        self.assertEqual(panel.name.text(), "No movie selected...")
        self.assertIsNone(panel.yt_code)
        self.assertFalse(panel.trailer.isEnabled())
        self.assertFalse(panel.fav_button.isEnabled())

    def test_movie_link_cursor_reflects_availability(self):
        panel = MovieInfoBox(self.parent)

        panel.set_trailer_available(True)
        self.assertTrue(panel.trailer.isEnabled())
        self.assertEqual(panel.trailer.cursor().shape(), Qt.PointingHandCursor)

        panel.set_trailer_available(False)
        self.assertFalse(panel.trailer.isEnabled())
        self.assertEqual(panel.trailer.cursor().shape(), Qt.ArrowCursor)

    def test_live_epg_description_spans_all_columns(self):
        panel = LiveInfoBox(self.parent)
        program = QtWidgets.QTreeWidgetItem(["Date", "From", "To", "Name"])
        panel.live_EPG_info.addTopLevelItem(program)

        description = panel.add_epg_description(program, "Long description")

        self.assertTrue(description.isFirstColumnSpanned())
        self.assertIsNotNone(panel.live_EPG_info.itemWidget(description, 0))

    def test_live_epg_description_trims_outer_whitespace(self):
        panel = LiveInfoBox(self.parent)
        program = QtWidgets.QTreeWidgetItem(["Date", "From", "To", "Name"])
        panel.live_EPG_info.addTopLevelItem(program)

        description = panel.add_epg_description(
            program, "\n  First line\nSecond line  \n\n"
        )
        label = panel.live_EPG_info.itemWidget(description, 0)

        self.assertEqual(label.text(), "First line\nSecond line")
        self.assertIsNone(panel.add_epg_description(program, " \n\t "))

    def test_live_epg_description_trims_outer_invisible_characters(self):
        panel = LiveInfoBox(self.parent)
        program = QtWidgets.QTreeWidgetItem(["Date", "From", "To", "Name"])
        panel.live_EPG_info.addTopLevelItem(program)

        description = panel.add_epg_description(
            program, "\u200bDescription\u200b\ufeff"
        )
        label = panel.live_EPG_info.itemWidget(description, 0)

        self.assertEqual(label.text(), "Description")

    def test_movie_description_uses_full_width_and_scrolls_as_needed(self):
        panel = MovieInfoBox(self.parent)

        position = panel.layout.getItemPosition(
            panel.layout.indexOf(panel.description)
        )

        self.assertEqual(position, (10, 0, 1, 2))
        self.assertEqual(panel.description_title.text(), "Description:")
        self.assertEqual(
            panel.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded
        )

    def test_series_reset_clears_stale_selection(self):
        panel = SeriesInfoBox(self.parent)
        panel.name.setText("Old series")
        panel.tmdb_code = "123"
        panel.fav_button.setEnabled(True)

        panel.reset()

        self.assertEqual(panel.name.text(), "No series selected...")
        self.assertIsNone(panel.tmdb_code)
        self.assertFalse(panel.tmdb.isEnabled())
        self.assertFalse(panel.fav_button.isEnabled())

    def test_series_link_cursor_reflects_availability(self):
        panel = SeriesInfoBox(self.parent)

        panel.set_tmdb_available(True)
        self.assertTrue(panel.tmdb.isEnabled())
        self.assertEqual(panel.tmdb.cursor().shape(), Qt.PointingHandCursor)

        panel.reset()
        self.assertEqual(panel.tmdb.cursor().shape(), Qt.ArrowCursor)

    def test_series_description_uses_full_width_and_scrolls_as_needed(self):
        panel = SeriesInfoBox(self.parent)

        position = panel.layout.getItemPosition(
            panel.layout.indexOf(panel.description)
        )

        self.assertEqual(position, (10, 0, 1, 2))
        self.assertEqual(panel.description_title.text(), "Description:")
        self.assertEqual(
            panel.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded
        )


if __name__ == "__main__":
    unittest.main()
