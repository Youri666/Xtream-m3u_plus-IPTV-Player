"""Regression coverage for grouped series history and existing episode navigation."""

import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QTreeWidget, QAbstractItemView

from iptv_player.ui.history import GROUP_ROLE, populate_history_tree, selected_history_entries


class HistoryGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.entries = [
            {'key': 'Series:3', 'type': 'Series', 'series_id': '10',
             'series_title': 'Show', 'title': 'Episode 3', 'last_viewed': 'newest'},
            {'key': 'Series:2', 'type': 'Series', 'series_id': '20',
             'series_title': 'Show', 'title': 'Other episode', 'last_viewed': 'middle'},
            {'key': 'Series:1', 'type': 'Series', 'series_id': '10',
             'series_title': 'Show', 'title': 'Episode 1', 'last_viewed': 'oldest'},
            {'key': 'Series:legacy', 'type': 'Series', 'title': 'Legacy episode'},
        ]

    def tearDown(self):
        self.tree.close()

    def populate(self, entries=None, preserve_state=True):
        populate_history_tree(self.tree, self.entries if entries is None else entries,
                              str, group_series=True, preserve_state=preserve_state)

    def test_groups_by_id_with_newest_episode_on_parent_and_keeps_legacy_rows(self):
        self.populate()
        self.assertEqual(self.tree.topLevelItemCount(), 3)
        group = self.tree.topLevelItem(0)
        self.assertEqual((group.text(0), group.text(1)), ('newest', 'Show'))
        self.assertEqual(group.childCount(), 2)
        self.assertEqual(group.data(0, Qt.UserRole)['key'], 'Series:3')
        self.assertEqual(group.child(1).data(0, Qt.UserRole)['key'], 'Series:1')
        self.assertEqual(self.tree.topLevelItem(1).data(0, GROUP_ROLE), '20')
        self.assertEqual(self.tree.topLevelItem(2).text(1), 'Legacy episode')

    def test_group_removal_includes_all_its_episodes_and_deduplicates_selection(self):
        self.populate()
        group = self.tree.topLevelItem(0)
        self.assertEqual({entry['key'] for entry in selected_history_entries([group, group.child(0)])},
                         {'Series:3', 'Series:1'})
        self.assertEqual(selected_history_entries([group.child(1)]), [self.entries[2]])

    def test_refresh_keeps_expansion_and_selection_when_latest_episode_changes(self):
        self.populate()
        group = self.tree.topLevelItem(0)
        group.setExpanded(True)
        self.tree.setCurrentItem(group.child(1))
        latest = dict(self.entries[0], key='Series:4', title='Episode 4')
        self.populate([latest] + self.entries)
        group = self.tree.topLevelItem(0)
        self.assertTrue(group.isExpanded())
        self.assertEqual(group.data(0, Qt.UserRole)['key'], 'Series:4')
        self.assertEqual(self.tree.currentItem().data(0, Qt.UserRole)['key'], 'Series:1')
        self.assertTrue(self.tree.currentItem().isSelected())

    def test_account_change_does_not_carry_expansion_or_selection(self):
        self.populate()
        self.tree.topLevelItem(0).setExpanded(True)
        self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.populate(preserve_state=False)
        self.assertFalse(self.tree.topLevelItem(0).isExpanded())
        self.assertEqual(self.tree.selectedItems(), [])

    def test_live_and_movie_rows_remain_flat(self):
        populate_history_tree(self.tree, self.entries[:2], str, group_series=False)
        self.assertEqual(self.tree.topLevelItemCount(), 2)
        self.assertEqual(self.tree.topLevelItem(0).childCount(), 0)
        self.assertEqual(self.tree.topLevelItem(0).text(1), 'Episode 3')

    def test_group_and_child_activate_existing_navigation_with_correct_episode(self):
        source = Path(__file__).resolve().parents[1] / 'IPTVPlayer.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == 'IPTVPlayerApp')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == '_history_item_activated')
        namespace = {'Qt': Qt, 'load_history': lambda filename: self.entries}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
        harness = type('Harness', (), {'_history_item_activated': namespace['_history_item_activated']})()
        harness._process_embedded_player_events = Mock()
        harness._catalog_loaded = True
        harness.history_file = 'unused'
        harness._open_history_series = Mock(return_value=True)
        self.populate()
        group = self.tree.topLevelItem(0)
        harness._history_item_activated(group)
        harness._open_history_series.assert_called_with(self.entries[0])
        harness._history_item_activated(group.child(1))
        harness._open_history_series.assert_called_with(self.entries[2])
