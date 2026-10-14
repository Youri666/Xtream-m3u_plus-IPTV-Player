"""Cached tooltip summaries remain isolated and contain no provider secrets."""
import tempfile
import unittest
from pathlib import Path
from iptv_player.config.accounts import save_account, save_account_metadata, load_account_metadata
from iptv_player.ui.account_tooltips import account_tooltip


class AccountTooltipTests(unittest.TestCase):
    def test_cached_metadata_is_isolated_preserved_on_rename_and_has_no_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            credentials = ["https://example.test", "user", "password", "live", "movie", "series"]
            for name in ("A", "B"):
                save_account(filename, "manual", name, credentials)
            summary = save_account_metadata(filename, "A", {"status": "Active", "active_cons": 0,
                                            "max_connections": 2, "exp_date": "1900000000",
                                            "password": "secret", "token": "secret-token"})
            self.assertNotIn("password", summary)
            self.assertNotIn("token", summary)
            self.assertEqual(load_account_metadata(filename, "B"), {})
            self.assertEqual(load_account_metadata(filename, "A"), summary)
            save_account(filename, "manual", "Renamed", credentials, old_name="A")
            self.assertEqual(load_account_metadata(filename, "Renamed"), summary)
            self.assertIn("Active connections (last known): 0", account_tooltip(summary))

    def test_unknown_and_malformed_dates_are_safe(self):
        self.assertEqual(account_tooltip({}), "Account information not available yet")
        tooltip = account_tooltip({"status": "<b>provider</b>", "exp_date": "invalid", "refreshed_at": "bad"})
        self.assertIn("&lt;b&gt;provider&lt;/b&gt;", tooltip)
        self.assertIn("Expiry: Unknown", tooltip)
        self.assertIn("Last refreshed: Unknown", tooltip)

    def test_host_and_timezone_are_from_the_same_cached_response(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            save_account(filename, "manual", "A", ["https://example.test", "user", "password", "live", "movie", "series"])
            save_account_metadata(filename, "A", {"status": "Active"},
                                  {"url": "example.test", "port": "80", "timezone": "Europe/Brussels", "token": "secret"})
            summary = load_account_metadata(filename, "A")
            tooltip = account_tooltip(summary)
            self.assertIn("Host: example.test:80", tooltip)
            self.assertIn("Timezone: Europe/Brussels", tooltip)
            self.assertNotIn("secret", tooltip)
