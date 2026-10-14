"""Account popup requests are bounded, independent and preserve cached information."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PyQt5.QtWidgets import QApplication
from iptv_player.config.accounts import save_account, save_account_metadata, load_account_metadata
from iptv_player.provider.account_metadata import AccountMetadataLoader


class MetadataLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_refresh_includes_cached_accounts_and_throttles_repeated_openings(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            credentials = ["https://example.test", "user", "pass", "live", "movie", "series"]
            save_account(filename, "manual", "A", credentials, user_agent="Agent A")
            save_account(filename, "manual", "B", credentials, user_agent="Agent B")
            save_account_metadata(filename, "A", {"status": "Active"})
            loader = AccountMetadataLoader(filename)
            loader.pool = Mock()
            with patch("iptv_player.provider.account_metadata.time.monotonic", return_value=100):
                loader.refresh()
                loader.refresh()
                self.assertEqual(loader.pool.start.call_count, 2)
                self.assertEqual({worker.user_agent for worker in loader.pending.values()}, {"Agent A", "Agent B"})
                for key in list(loader.pending):
                    name = "A" if key[2] == "Agent A" else "B"
                    loader._finished(name, key, {"user_info": {"status": "Active", "active_cons": 0}})
                loader.refresh()
                self.assertEqual(loader.pool.start.call_count, 2)
            with patch("iptv_player.provider.account_metadata.time.monotonic", return_value=131):
                loader.refresh()
                self.assertEqual(loader.pool.start.call_count, 4)

    def test_failed_refresh_preserves_cache_and_edited_account_discards_old_response(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            credentials = ["https://example.test", "user", "pass", "live", "movie", "series"]
            save_account(filename, "manual", "A", credentials)
            original = save_account_metadata(filename, "A", {"status": "Active"})
            loader = AccountMetadataLoader(filename)
            loader.pool = Mock()
            loader.refresh()
            key = next(iter(loader.pending))
            loader._finished("A", key, None)
            self.assertEqual(load_account_metadata(filename, "A"), original)
            save_account(filename, "manual", "A", credentials, user_agent="Edited")
            loader._finished("A", key, {"user_info": {"status": "Expired"}})
            self.assertEqual(load_account_metadata(filename, "A"), original)
