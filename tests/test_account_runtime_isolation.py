"""Regression checks for delayed requests and the reusable internal player."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from iptv_player.provider.workers import MovieInfoFetcher, SeriesInfoFetcher, EPGWorker
from iptv_player.ui.player import EmbeddedPlayerWindow


def info_callbacks():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "IPTVPlayer.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "IPTVPlayerApp")
    names = {"_account_info_refresh_finished", "_account_info_refresh_failed"}
    module = ast.Module(body=[node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(module), "info_callbacks", "exec"), namespace)
    return namespace


class AccountRuntimeIsolationTests(unittest.TestCase):
    def test_queued_provider_requests_keep_original_header(self):
        for cls, fields, response in (
            (MovieInfoFetcher, ("1",), {"info": {}, "movie_data": {}}),
            (SeriesInfoFetcher, ("1", False), {}),
            (EPGWorker, ("1",), {"epg_listings": []}),
        ):
            with self.subTest(worker=cls.__name__):
                parent = SimpleNamespace(current_user_agent="Account A")
                worker = cls("https://example.test", "user", "password", *fields, parent=parent)
                parent.current_user_agent = "Account B"
                with patch("iptv_player.provider.workers.XtreamClient") as client:
                    client.return_value.__enter__.return_value.get_json.return_value = response
                    worker.run()
                    self.assertEqual(client.call_args.args[3], "Account A")

    def test_old_info_success_and_failure_leave_new_refresh_untouched(self):
        callbacks = info_callbacks()
        window = SimpleNamespace(_account_info_generation=2,
                                 account_info_refresh_in_progress=True,
                                 account_info_worker=object(),
                                 refresh_account_info_button=Mock(),
                                 account_info_last_refresh_label=Mock(),
                                 update_account_info=Mock())
        pending_worker = window.account_info_worker
        callbacks["_account_info_refresh_finished"](window, {"old": True}, 1)
        callbacks["_account_info_refresh_failed"](window, "old error", 1)
        self.assertTrue(window.account_info_refresh_in_progress)
        self.assertIs(window.account_info_worker, pending_worker)
        window.update_account_info.assert_not_called()
        window.refresh_account_info_button.setEnabled.assert_not_called()
        window.account_info_last_refresh_label.setText.assert_not_called()
        callbacks["_account_info_refresh_finished"](window, {"current": True}, 2)
        window.update_account_info.assert_called_once_with({"current": True})
        self.assertFalse(window.account_info_refresh_in_progress)

    def test_reused_player_overrides_header_for_every_new_media(self):
        window = Mock()
        window.isVisible.return_value = True
        window._network_caching_ms = 1000
        window._audio_language = ""
        window._subtitle_language = ""
        window._media_generation = 0
        window._playlist = []
        window._user_agent = "Old account"
        for agent in ("Account A", "Account B"):
            EmbeddedPlayerWindow.set_user_agent(window, agent)
            window.instance.media_new.return_value.add_option.reset_mock()
            EmbeddedPlayerWindow.play_url(window, "https://example.test/stream", "Example", [])
            window.instance.media_new.return_value.add_option.assert_any_call(":http-user-agent=" + agent)
            options = [call.args[0] for call in window.instance.media_new.return_value.add_option.call_args_list]
            self.assertNotIn(":http-user-agent=Old account", options)
