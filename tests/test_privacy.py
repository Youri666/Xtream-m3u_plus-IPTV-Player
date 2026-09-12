import unittest

from iptv_player.utils.privacy import private_url_log_reference


class PrivateUrlLogReferenceTests(unittest.TestCase):
    def test_hides_host_and_credentials(self):
        result = private_url_log_reference(
            "https://provider.example/series/username/password/953691.mkv"
        )
        self.assertEqual(result, "<private URL ending in 953691.mkv>")
        self.assertNotIn("provider", result)
        self.assertNotIn("username", result)
        self.assertNotIn("password", result)

    def test_handles_url_without_final_component(self):
        self.assertEqual(
            private_url_log_reference("https://provider.example"),
            "<private URL ending in unknown>",
        )


if __name__ == "__main__":
    unittest.main()

