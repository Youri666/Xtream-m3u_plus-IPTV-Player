import tempfile
import unittest
from pathlib import Path

from iptv_player.provider.cache import (
    account_cache_file,
    account_cache_key,
    build_catalog_cache,
    catalog_cache_is_fresh,
    load_catalog_cache,
    write_catalog_cache,
)


class ProviderCacheTests(unittest.TestCase):
    def setUp(self):
        self.enabled = {"LIVE": True, "Movies": False, "Series": False}
        self.account_key = account_cache_key("HTTPS://Example.test/", "viewer")
        self.cache = {
            "_metadata": {
                "schema_version": 1,
                "account_key": self.account_key,
                "fetched_at": 1_000,
            },
            "LIVE categories": [],
            "LIVE": [],
        }

    def test_account_key_normalizes_server_case_and_trailing_slash(self):
        self.assertEqual(
            self.account_key,
            account_cache_key("https://example.test", "viewer"),
        )
        self.assertNotEqual(
            self.account_key,
            account_cache_key("https://example.test", "another-user"),
        )

    def test_each_account_uses_a_dedicated_cache_file(self):
        base_file = Path("data") / "provider_catalog_cache.json"
        first = account_cache_file(base_file, "first-account")
        second = account_cache_file(base_file, "second-account")

        self.assertEqual(
            first,
            Path("data") / "provider_catalog_cache.first-account.json",
        )
        self.assertNotEqual(first, second)

    def test_fresh_cache_requires_matching_account_and_all_enabled_data(self):
        self.assertTrue(
            catalog_cache_is_fresh(
                self.cache, self.account_key, self.enabled, 1, current_time=1_100
            )
        )
        self.assertFalse(
            catalog_cache_is_fresh(
                self.cache, "another-account", self.enabled, 1, current_time=1_100
            )
        )
        incomplete = dict(self.cache)
        incomplete.pop("LIVE")
        self.assertFalse(
            catalog_cache_is_fresh(
                incomplete, self.account_key, self.enabled, 1, current_time=1_100
            )
        )

    def test_expired_cache_is_rejected(self):
        self.assertFalse(
            catalog_cache_is_fresh(
                self.cache, self.account_key, self.enabled, 1, current_time=5_000
            )
        )

    def test_disabled_collections_are_preserved_for_same_account(self):
        previous = dict(self.cache)
        previous["Movies categories"] = [{"category_id": "1"}]
        previous["Movies"] = [{"stream_id": 2}]
        categories = {"LIVE": [{"category_id": "3"}], "Movies": [], "Series": []}
        entries = {"LIVE": [{"stream_id": 4}], "Movies": [], "Series": []}

        result = build_catalog_cache(
            previous,
            self.account_key,
            categories,
            entries,
            self.enabled,
            fetch_complete=True,
            fetched_at=2_000,
        )

        self.assertEqual(result["Movies"], previous["Movies"])
        self.assertEqual(result["LIVE"], entries["LIVE"])
        self.assertEqual(result["_metadata"]["fetched_at"], 2_000)

    def test_cache_round_trip_and_invalid_json_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "catalog.json"
            write_catalog_cache(filename, self.cache)
            self.assertEqual(load_catalog_cache(filename), self.cache)

            filename.write_text("not json", encoding="utf-8")
            self.assertEqual(load_catalog_cache(filename), {})


if __name__ == "__main__":
    unittest.main()

