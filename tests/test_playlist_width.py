"""Opening a wide playlist must not increase the player's window geometry."""
import os
import unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QLineEdit
from iptv_player.ui.player import EmbeddedPlayerWindow, _PlaylistSidebar


class PlaylistWidthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_show_resize_and_hide_keep_window_size(self):
        window = QMainWindow()
        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = _PlaylistSidebar()
        sidebar_layout = QVBoxLayout(sidebar)
        playlist = QListWidget()
        playlist.addItem("A very long episode title " * 20)
        sidebar_layout.addWidget(QLineEdit())
        sidebar_layout.addWidget(playlist)
        video = QWidget()
        video.setMinimumSize(640, 360)
        layout.addWidget(sidebar)
        layout.addWidget(video, 1)
        sidebar.hide()
        window.setCentralWidget(content)
        window.sidebar = sidebar
        window.playlist_list = playlist
        window.video_frame = video
        window._content_widget = content
        window._content_layout = layout
        window._playlist_width_hint = 2000
        window._is_fullscreen = False
        window.resize(800, 500)
        window.show()
        self.app.processEvents()
        before = window.size()
        EmbeddedPlayerWindow._update_sidebar_width(window)
        sidebar.show()
        self.app.processEvents()
        self.assertEqual(window.size(), before)
        self.assertLessEqual(sidebar.width(), before.width() - video.minimumWidth())
        window.resize(760, 500)
        self.app.processEvents()
        EmbeddedPlayerWindow._update_sidebar_width(window)
        self.app.processEvents()
        sidebar.hide()
        self.app.processEvents()
        self.assertEqual(window.width(), 760)
        window.close()

    def test_short_titles_do_not_have_a_fixed_minimum_width(self):
        window = QMainWindow()
        content = QWidget()
        content.resize(1200, 500)
        window.setCentralWidget(content)
        sidebar = _PlaylistSidebar()
        sidebar_layout = QVBoxLayout(sidebar)
        playlist = QListWidget()
        playlist.addItem("1. TV")
        sidebar_layout.addWidget(QLineEdit())
        sidebar_layout.addWidget(playlist)
        window.sidebar = sidebar
        window.playlist_list = playlist
        window.video_frame = QWidget()
        window.video_frame.setMinimumWidth(640)
        window._content_widget = content
        window._content_layout = QHBoxLayout(content)
        window._content_layout.setContentsMargins(0, 0, 0, 0)
        window._content_layout.setSpacing(0)
        window._is_fullscreen = False
        window._playlist_width_hint = playlist.sizeHintForColumn(0)
        EmbeddedPlayerWindow._update_sidebar_width(window)
        short_width = sidebar.maximumWidth()
        self.assertLess(short_width, 240)
        playlist.clear()
        playlist.addItem("1. A considerably longer episode title")
        window._playlist_width_hint = playlist.sizeHintForColumn(0)
        EmbeddedPlayerWindow._update_sidebar_width(window)
        self.assertGreater(sidebar.maximumWidth(), short_width)
        window.close()
