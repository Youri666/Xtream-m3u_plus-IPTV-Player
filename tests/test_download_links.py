import unittest

from iptv_player.download_links import (
    download_link_text,
    flatten_series_episodes,
    safe_download_filename,
    structured_download_text,
)


class DownloadLinkTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
