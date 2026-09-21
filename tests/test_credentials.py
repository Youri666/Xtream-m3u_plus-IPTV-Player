import unittest

from iptv_player.provider.credentials import parse_xtream_m3u_url


class XtreamCredentialParsingTests(unittest.TestCase):
    def test_accepts_prefixed_path_port_and_any_query_order(self):
        result = parse_xtream_m3u_url(
            "https://provider.example:8443/api/get.php?output=ts&password=secret&username=user"
        )

        self.assertEqual(
            result,
            ("https://provider.example:8443", "user", "secret"),
        )

    def test_decodes_escaped_credentials(self):
        result = parse_xtream_m3u_url(
            "http://provider.example/get.php?username=user%40mail&password=a%2Bb"
        )

        self.assertEqual(result, ("http://provider.example", "user@mail", "a+b"))

    def test_rejects_invalid_or_incomplete_urls(self):
        invalid_urls = (
            "provider.example/get.php?username=user&password=secret",
            "https://provider.example/player.php?username=user&password=secret",
            "https://provider.example/get.php?username=user",
        )

        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertIsNone(parse_xtream_m3u_url(url))


if __name__ == "__main__":
    unittest.main()
