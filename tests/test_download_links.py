import unittest

from iptv_player.download_links import (
    download_link_text,
    export_restriction,
    flatten_series_episodes,
    m3u_playlist_text,
    safe_download_filename,
    structured_download_text,
)


class DownloadLinkTests(unittest.TestCase):
    def test_blocks_all_category_exports_until_explicitly_enabled(self):
        restriction, series_count = export_restriction(
            [{"scope": "movie"}],
            includes_all=True,
            allow_all_category_exports=False,
            max_series_per_export=10,
        )

        self.assertEqual(restriction, "all_disabled")
        self.assertEqual(series_count, 0)

    def test_limits_only_complete_series_requests(self):
        restriction, series_count = export_restriction(
            ([{"scope": "series"}] * 11)
            + [{"scope": "season"}, {"scope": "episode"}],
            includes_all=False,
            allow_all_category_exports=False,
            max_series_per_export=10,
        )

        self.assertEqual(restriction, "series_limit")
        self.assertEqual(series_count, 11)

    def test_all_series_export_requires_both_safety_overrides(self):
        restriction, series_count = export_restriction(
            [{"scope": "series"}] * 12,
            includes_all=True,
            allow_all_category_exports=True,
            max_series_per_export=10,
        )

        self.assertEqual(restriction, "series_limit")
        self.assertEqual(series_count, 12)

        restriction, series_count = export_restriction(
            [{"scope": "series"}] * 12,
            includes_all=True,
            allow_all_category_exports=True,
            max_series_per_export=20,
        )

        self.assertIsNone(restriction)
        self.assertEqual(series_count, 12)

    def test_flattens_episodes_in_natural_season_order(self):
        episodes = {
            "10": [{"id": 1001}],
            "2": [{"id": 201}, {"id": 202}],
            "Specials": [{"id": 1}],
        }

        self.assertEqual(
            [episode["id"] for episode in flatten_series_episodes(episodes)],
            [201, 202, 1001, 1],
        )

    def test_creates_portable_text_filename(self):
        self.assertEqual(
            safe_download_filename('Show: Season 1/2?'),
            "Show_ Season 1_2_.txt",
        )
        self.assertEqual(safe_download_filename("..."), "download-links.txt")
        self.assertEqual(
            safe_download_filename("My playlist", extension=".m3u"),
            "My playlist.m3u",
        )

    def test_creates_extended_m3u_playlist_with_titles_and_groups(self):
        text = m3u_playlist_text([
            {
                "title": "Episode 01\nPilot",
                "group_title": 'Example "Series"',
                "url": "https://example/episode-01.mkv",
            },
            {
                "title": "Movie",
                "group_title": None,
                "url": "https://example/movie.mkv",
            },
        ])

        self.assertEqual(
            text,
            "#EXTM3U\n"
            "#EXTINF:-1 group-title=\"Example 'Series'\",Episode 01 Pilot\n"
            "https://example/episode-01.mkv\n"
            "#EXTINF:-1,Movie\n"
            "https://example/movie.mkv\n",
        )

    def test_serializes_one_nonempty_url_per_line(self):
        self.assertEqual(
            download_link_text([" https://one ", "", "https://two"]),
            "https://one\nhttps://two",
        )

    def test_formats_series_file_with_seasons_and_named_episodes(self):
        text = structured_download_text(
            "Example Series",
            [
                {
                    "group_title": None,
                    "season": "1",
                    "episode_number": "1",
                    "title": "Pilot",
                    "url": "https://one",
                },
                {
                    "season": "2",
                    "episode_number": "3",
                    "title": "Return",
                    "url": "https://two",
                },
            ],
        )

        self.assertEqual(
            text,
            "Example Series\n\n"
            "Season 01\n\n"
            "Episode 01 - Pilot\n"
            "https://one\n\n"
            "Season 02\n\n"
            "Episode 03 - Return\n"
            "https://two\n",
        )

    def test_formats_single_movie_as_title_and_url(self):
        self.assertEqual(
            structured_download_text(
                "Example Movie",
                [{"title": "Example Movie", "url": "https://movie"}],
            ),
            "Example Movie\n\nhttps://movie\n",
        )

    def test_groups_multiple_series_in_one_file(self):
        text = structured_download_text(
            "2 selected series",
            [
                {
                    "group_title": "First Series",
                    "season": "1",
                    "episode_number": "1",
                    "title": "Pilot",
                    "url": "https://one",
                },
                {
                    "group_title": "Second Series",
                    "season": "2",
                    "episode_number": "3",
                    "title": "Return",
                    "url": "https://two",
                },
            ],
        )

        self.assertEqual(
            text,
            "2 selected series\n\n"
            "First Series\n\n"
            "Season 01\n\n"
            "Episode 01 - Pilot\n"
            "https://one\n\n"
            "Second Series\n\n"
            "Season 02\n\n"
            "Episode 03 - Return\n"
            "https://two\n",
        )


if __name__ == "__main__":
    unittest.main()
