import unittest

from iptv_player.provider.streams import generate_stream_url


class StreamUrlTests(unittest.TestCase):
    def test_uses_live_template_and_extension(self):
        result = generate_stream_url(
            "https://provider.example",
            "viewer",
            "secret",
            "live",
            42,
            "ts",
            "{server}/live/{username}/{password}/{stream_id}.{container_extension}",
            "unused",
        )
        self.assertEqual(
            result,
            "https://provider.example/live/viewer/secret/42.ts",
        )

    def test_template_without_extension_does_not_append_one(self):
        result = generate_stream_url(
            "https://provider.example",
            "viewer",
            "secret",
            "movie",
            24,
            "mkv",
            "unused",
            "{server}/play/{username}/{password}/{stream_id}",
        )
        self.assertEqual(result, "https://provider.example/play/viewer/secret/24")

    def test_unknown_type_uses_legacy_fallback(self):
        result = generate_stream_url(
            "https://provider.example",
            "viewer",
            "secret",
            "archive",
            7,
            "mp4",
            "unused",
            "unused",
        )
        self.assertEqual(
            result,
            "https://provider.example/archive/viewer/secret/7.mp4",
        )


if __name__ == "__main__":
    unittest.main()

