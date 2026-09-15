from pathlib import Path
import tempfile
import unittest

from iptv_player.provider.cache import account_cache_file
from iptv_player.storage import (
    account_favorites_file,
    provider_preferences_file,
    remove_account_data_files,
)


class AccountCleanupTests(unittest.TestCase):
    def test_deleting_account_removes_its_three_owned_json_files(self):
        with tempfile.TemporaryDirectory() as directory:
            data_directory = Path(directory)
            cache_base = data_directory / "provider_catalog_cache.json"
            favorites_base = data_directory / "provider_favorites.json"
            preferences_base = data_directory / "provider_preferences.json"
            account_id = "account123"
            owned_files = (
                account_cache_file(cache_base, account_id),
                account_favorites_file(favorites_base, account_id),
                provider_preferences_file(preferences_base, account_id),
            )
            for filename in owned_files:
                Path(filename).write_text("{}", encoding="utf-8")

            failures = remove_account_data_files(
                account_id, cache_base, favorites_base, preferences_base
            )

            self.assertEqual(failures, [])
            self.assertTrue(all(not Path(filename).exists() for filename in owned_files))


if __name__ == "__main__":
    unittest.main()
