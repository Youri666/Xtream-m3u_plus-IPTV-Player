from types import SimpleNamespace
import unittest

from iptv_player.provider.workers import FetchDataWorker


class FetchDataWorkerTests(unittest.TestCase):
    def test_snapshots_account_files_before_provider_switch(self):
        parent = SimpleNamespace(
            current_user_agent="Original agent",
            cache_file="provider_catalog_cache.json",
            legacy_cache_file="all_cached_data.json",
            active_account_id="first-account",
            favorites_file="provider_favorites.first-account.json",
        )
        worker = FetchDataWorker(
            "http://provider.test",
            "user",
            "password",
            "live-format",
            "movie-format",
            "series-format",
            parent,
        )

        parent.current_user_agent = "New agent"
        parent.active_account_id = "second-account"
        parent.favorites_file = "provider_favorites.second-account.json"

        self.assertEqual(worker.user_agent, "Original agent")
        self.assertEqual(worker.cache_file_identifier, "first-account")
        self.assertEqual(
            worker.favorites_file,
            "provider_favorites.first-account.json",
        )


if __name__ == "__main__":
    unittest.main()
