from pathlib import Path
import tempfile
import unittest

from iptv_player.config.accounts import (
    delete_account,
    load_account,
    load_accounts,
    load_startup_account,
    parse_account,
    save_account,
    save_startup_account,
)


class AccountStorageTests(unittest.TestCase):
    def test_saves_accounts_and_preserves_label_case(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"

            save_account(
                str(file_path),
                "manual",
                "Living Room",
                ["host", "user", "password", "live", "movie", "series"],
            )

            self.assertEqual(list(load_accounts(str(file_path))), ["Living Room"])
            self.assertEqual(
                load_account(str(file_path), "Living Room"),
                "manual|host|user|password|live|movie|series",
            )

    def test_rename_updates_startup_account(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            save_account(str(file_path), "m3u_plus", "Old name", ["url", "l", "m", "s"])
            save_startup_account(str(file_path), "Old name")

            save_account(
                str(file_path),
                "m3u_plus",
                "New name",
                ["url", "l", "m", "s"],
                old_name="Old name",
            )

            self.assertIsNone(load_account(str(file_path), "Old name"))
            self.assertIsNotNone(load_account(str(file_path), "New name"))
            self.assertEqual(load_startup_account(str(file_path)), "New name")

    def test_delete_clears_startup_account(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            save_account(str(file_path), "m3u_plus", "Default", ["url", "l", "m", "s"])
            save_startup_account(str(file_path), "Default")

            self.assertTrue(delete_account(str(file_path), "Default"))
            self.assertEqual(load_startup_account(str(file_path)), "None")
            self.assertFalse(delete_account(str(file_path), "Missing"))

    def test_parses_supported_accounts_and_rejects_malformed_data(self):
        self.assertEqual(
            parse_account("manual|host|user|password|live|movie|series"),
            ("manual", ["host", "user", "password", "live", "movie", "series"]),
        )
        self.assertEqual(
            parse_account("m3u_plus|url|live|movie|series"),
            ("m3u_plus", ["url", "live", "movie", "series"]),
        )
        self.assertIsNone(parse_account("manual|missing|fields"))
        self.assertIsNone(parse_account("unknown|value"))


if __name__ == "__main__":
    unittest.main()
