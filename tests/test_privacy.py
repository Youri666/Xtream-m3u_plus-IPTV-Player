import unittest

from iptv_player.utils.privacy import private_url_log_reference, redact_log_credentials


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

    def test_redacts_query_credentials_from_network_errors(self):
        message = (
            "Request failed for http://provider/player_api.php?"
            "username=Maestro&password=s3cret&action=get_live_streams"
        )

        redacted = redact_log_credentials(message)

        self.assertIn("username=***", redacted)
        self.assertIn("password=***", redacted)
        self.assertNotIn("Maestro", redacted)
        self.assertNotIn("s3cret", redacted)

    def test_redacts_labeled_and_stream_path_credentials(self):
        message = (
            "Username: Maestro Password: s3cret "
            "http://provider/series/Maestro/s3cret/123.mkv"
        )

        redacted = redact_log_credentials(message)

        self.assertIn("Username: ***", redacted)
        self.assertIn("Password: ***", redacted)
        self.assertIn("/series/***/***/123.mkv", redacted)
        self.assertNotIn("Maestro", redacted)
        self.assertNotIn("s3cret", redacted)


if __name__ == "__main__":
    unittest.main()

