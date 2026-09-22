from pathlib import Path
import tempfile
import unittest

from iptv_player.config.accounts import (
    account_name_error,
    delete_account,
    load_account,
    load_account_epg_offset,
    load_account_id,
    load_accounts,
    load_startup_account,
    parse_account,
    save_account,
    save_startup_account,
)


class AccountStorageTests(unittest.TestCase):
    def test_rejects_only_reserved_or_multiline_account_names(self):
        self.assertIsNotNone(account_name_error("None"))
        self.assertIsNotNone(account_name_error("two\nlines"))
        self.assertIsNone(account_name_error("Living Room - Été"))
        self.assertIsNone(account_name_error("Provider = Main: #1"))

    def test_storage_rejects_unsafe_account_name(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            with self.assertRaises(ValueError):
                save_account(
                    str(file_path),
                    "m3u_plus",
                    "invalid\nname",
                    ["url", "live", "movie", "series"],
                )

    def test_loads_legacy_lowercase_key_from_mixed_case_startup_name(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            file_path.write_text(
                "[Credentials]\n"
                "maestro = manual|host|user|password|live|movie|series\n\n"
                "[Startup credentials]\n"
                "startup_credentials = Maestro\n",
                encoding="utf-8",
            )

            self.assertEqual(list(load_accounts(str(file_path))), ["Maestro"])
            self.assertIsNotNone(load_account(str(file_path), "Maestro"))

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
            self.assertEqual(len(load_account_id(str(file_path), "Living Room")), 32)
            self.assertEqual(
                load_account(str(file_path), "Living Room"),
                "manual|host|user|password|live|movie|series",
            )
            self.assertEqual(load_account_epg_offset(str(file_path), "Living Room"), 0)

    def test_epg_offset_is_account_specific_and_survives_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            save_account(
                str(file_path),
                "m3u_plus",
                "Old name",
                ["url", "live", "movie", "series"],
                epg_offset_minutes=90,
            )

            self.assertEqual(load_account_epg_offset(str(file_path), "Old name"), 90)
            save_account(
                str(file_path),
                "m3u_plus",
                "New name",
                ["url", "live", "movie", "series"],
                old_name="Old name",
                epg_offset_minutes=-30,
            )
            self.assertEqual(load_account_epg_offset(str(file_path), "New name"), -30)

    def test_epg_offset_uses_safe_defaults_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            save_account(
                str(file_path),
                "m3u_plus",
                "Bounded",
                ["url", "live", "movie", "series"],
                epg_offset_minutes=1_000,
            )
            self.assertEqual(load_account_epg_offset(str(file_path), "Bounded"), 720)
            self.assertEqual(load_account_epg_offset(str(file_path), "Missing"), 0)

    def test_name_punctuation_is_stored_as_display_data(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            name = "Provider = Main: #1"

            save_account(
                str(file_path),
                "m3u_plus",
                name,
                ["url", "live", "movie", "series"],
            )

            self.assertEqual(list(load_accounts(str(file_path))), [name])

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

    def test_rename_and_delete_match_legacy_names_without_case(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            file_path.write_text(
                "[Credentials]\n"
                "maestro = m3u_plus|url|live|movie|series\n\n"
                "[Startup credentials]\n"
                "startup_credentials = Maestro\n",
                encoding="utf-8",
            )

            save_account(
                str(file_path),
                "m3u_plus",
                "Living Room",
                ["url", "live", "movie", "series"],
                old_name="Maestro",
            )
            self.assertIsNone(load_account(str(file_path), "Maestro"))
            self.assertIsNotNone(load_account(str(file_path), "Living Room"))
            self.assertEqual(load_startup_account(str(file_path)), "Living Room")
            self.assertTrue(delete_account(str(file_path), "living room"))

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
