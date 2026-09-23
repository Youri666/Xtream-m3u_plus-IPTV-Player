import unittest
from unittest.mock import Mock

from iptv_player.provider.tmdb import TmdbClient, normalize_tmdb_details


class TmdbClientTests(unittest.TestCase):
    def test_token_is_sent_in_header_instead_of_url(self):
        response = Mock()
        response.json.return_value = {}
        request_get = Mock(return_value=response)

        TmdbClient("secret-token", (3, 5), request_get).test_connection()

        url = request_get.call_args.args[0]
        kwargs = request_get.call_args.kwargs
        self.assertNotIn("secret-token", url)
        self.assertEqual(
            kwargs["headers"]["Authorization"], "Bearer secret-token"
        )

    def test_normalizes_movie_metadata(self):
        normalized = normalize_tmdb_details("movie", {
            "title": "Movie",
            "release_date": "2026-01-02",
            "genres": [{"name": "Drama"}],
            "runtime": 95,
            "vote_average": 7.5,
            "overview": "Plot",
            "poster_path": "/poster.jpg",
            "credits": {
                "crew": [{"job": "Director", "name": "Director Name"}],
                "cast": [{"name": "Actor Name"}],
            },
            "videos": {
                "results": [{"site": "YouTube", "type": "Trailer", "key": "abc"}]
            },
        })

        self.assertEqual(normalized["name"], "Movie")
        self.assertEqual(normalized["director"], "Director Name")
        self.assertEqual(normalized["youtube_trailer"], "abc")
        self.assertTrue(normalized["poster_url"].endswith("/poster.jpg"))


if __name__ == "__main__":
    unittest.main()
