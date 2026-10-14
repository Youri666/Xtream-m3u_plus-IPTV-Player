"""Switching accounts refreshes visible Info without waiting for a tab change."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def account_activation():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "IPTVPlayer.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "IPTVPlayerApp")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "set_active_account")
    namespace = dict(logging=logging, CURRENT_VERSION="test", load_account_user_agent=lambda *args: "new agent",
                     load_account_id=lambda *args: "new-id", load_account_epg_offset=lambda *args: 0,
                     provider_preferences_file=lambda *args: "new-preferences", account_history_file=lambda *args: "new-history")
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "activation", "exec"), namespace)
    return namespace["set_active_account"]


class AccountInfoSwitchTests(unittest.TestCase):
    def make_window(self, visible):
        window = SimpleNamespace(active_account_name="Old", _catalog_request_generation=1,
                                 _account_info_generation=1, account_info_refresh_in_progress=True,
                                 account_info_worker=object(), refresh_account_info_button=Mock(),
                                 iptv_info_text=Mock(), account_info_last_refresh_label=Mock(),
                                 user_data_file="unused.ini", provider_preferences_base_file="prefs",
                                 history_base_file="history", tab_widget=Mock(),
                                 _tab_widgets_by_key=lambda: {}, _is_info_tab_visible=lambda: visible,
                                 account_info_auto_refresh_enabled=False, catalog_cache_enabled=True)
        for name in ("_reset_provider_view_state", "setWindowTitle", "_refresh_account_selectors",
                     "_load_hidden_categories", "_load_account_sort_preferences",
                     "_load_account_content_preferences", "_load_account_tab_preferences",
                     "refresh_history_tab", "_update_account_info_timer", "refresh_account_info"):
            setattr(window, name, Mock())
        return window

    def test_visible_info_refreshes_with_cache_and_periodic_refresh_disabled(self):
        window = self.make_window(True)
        seen_accounts = []
        window.refresh_account_info.side_effect = lambda: seen_accounts.append((window.active_account_name, window.current_user_agent))
        account_activation()(window, "New")
        self.assertEqual(seen_accounts, [("New", "new agent")])
        window.iptv_info_text.clear.assert_called_once()
        self.assertEqual(window._account_info_generation, 2)
        self.assertFalse(window.account_info_refresh_in_progress)
        window._update_account_info_timer.assert_called_once()

    def test_switch_outside_info_does_not_request_metadata(self):
        window = self.make_window(False)
        account_activation()(window, "New")
        window.refresh_account_info.assert_not_called()
        window.iptv_info_text.clear.assert_called_once()
