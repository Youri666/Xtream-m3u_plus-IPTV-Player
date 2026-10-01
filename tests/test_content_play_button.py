"""Verify that panel play buttons reuse selected-row catalog activation."""

import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap, QRegion
from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton


class Panel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.title_layout = QHBoxLayout(self)
        self.fav_button = QPushButton(self)
        self.fav_button.setFixedSize(32, 32)
        self.fav_button.setIconSize(QSize(24, 24))


def button_methods():
    source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'IPTVPlayerApp')
    names = {'init_info_boxes', '_update_content_play_button', '_activate_selected_content', '_content_play_icon'}
    specs = [{'info_box_class': Panel, 'stream_type': tab, 'attribute': tab.lower()}
             for tab in ('LIVE', 'Movies', 'Series')]
    namespace = {'CONTENT_TAB_SPECS': specs, 'QPushButton': QPushButton,
                 'QSize': QSize, 'QIcon': QIcon, 'Qt': Qt, 'QPixmap': QPixmap, 'QRegion': QRegion}
    module = ast.Module(body=[node for node in cls.body if isinstance(node, ast.FunctionDef)
                             and node.name in names], type_ignores=[])
    exec(compile(module, str(source), 'exec'), namespace)
    return {name: namespace[name] for name in names}


class ContentPlayButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.harness = type('Harness', (), button_methods())()
        self.harness.path_to_play_icon = str(Path(__file__).resolve().parents[1] / 'images/play_icon.png')
        self.harness.streaming_list_widgets = {tab: QListWidget() for tab in ('LIVE', 'Movies', 'Series')}
        self.harness.go_back_text = 'Go back'
        self.harness.series_navigation_level = 0
        self.harness.current_series_entry = None
        self.harness.streaming_item_double_clicked = Mock()
        self.harness.init_info_boxes()

    def tearDown(self):
        for panel in self.harness.info_boxes.values():
            panel.close()

    def test_play_button_dispatches_selected_row_once_for_every_tab(self):
        for tab in self.harness.streaming_list_widgets:
            if tab == 'Series':
                self.harness.series_navigation_level = 2
            widget = self.harness.streaming_list_widgets[tab]
            item = QListWidgetItem('Selected title')
            item.setData(Qt.UserRole, {'name': 'Selected title'})
            widget.addItem(item)
            widget.setCurrentItem(item)
            button = self.harness.info_boxes[tab].play_button
            self.assertTrue(button.isEnabled())
            self.assertFalse(button.icon().isNull())
            self.assertEqual(button.size(), self.harness.info_boxes[tab].fav_button.size())
            self.assertEqual(button.iconSize(), self.harness.info_boxes[tab].fav_button.iconSize())
            self.harness.streaming_item_double_clicked.reset_mock()
            button.click()
            self.harness.streaming_item_double_clicked.assert_called_once_with(item)

    def test_empty_placeholder_and_back_rows_never_activate(self):
        widget = self.harness.streaming_list_widgets['Series']
        button = self.harness.info_boxes['Series'].play_button
        self.assertFalse(button.isEnabled())
        for text, data in (('No items', None), ('Go back', {'id': 1})):
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, data)
            widget.addItem(item)
            widget.setCurrentItem(item)
            self.assertFalse(button.isEnabled())
            button.click()
        self.harness.streaming_item_double_clicked.assert_not_called()

    def test_play_button_is_hidden_for_seasons_and_visible_for_episodes(self):
        self.harness.series_navigation_level = 1
        widget = self.harness.streaming_list_widgets['Series']
        item = QListWidgetItem('Season 1')
        item.setData(Qt.UserRole, [{'id': 42}])
        widget.addItem(item)
        widget.setCurrentItem(item)
        button = self.harness.info_boxes['Series'].play_button
        self.assertTrue(button.isHidden())
        button.click()
        self.harness.streaming_item_double_clicked.assert_not_called()
        self.harness.series_navigation_level = 2
        self.harness._update_content_play_button('Series')
        self.assertFalse(button.isHidden())
        widget.clear()
        self.assertFalse(button.isEnabled())
        self.assertTrue(button.isHidden())

    def test_empty_selection_hides_details_and_controls(self):
        widget = self.harness.streaming_list_widgets['Movies']
        panel = self.harness.info_boxes['Movies']
        self.assertTrue(panel.isHidden())
        item = QListWidgetItem('Movie')
        item.setData(Qt.UserRole, {'id': 42})
        widget.addItem(item)
        widget.setCurrentItem(item)
        self.assertFalse(panel.isHidden())
        widget.clearSelection()
        self.assertTrue(panel.isHidden())
        self.assertTrue(panel.play_button.isHidden())
        self.assertTrue(panel.fav_button.isHidden())

    def test_series_details_remain_without_selected_episode(self):
        self.harness.current_series_entry = {'series_id': 42}
        self.harness.series_navigation_level = 2
        self.harness._update_content_play_button('Series')
        panel = self.harness.info_boxes['Series']
        self.assertFalse(panel.isHidden())
        self.assertTrue(panel.play_button.isHidden())
