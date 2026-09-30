import unittest
import io
import logging

from iptv_player.utils.privacy import private_url_log_reference, redact_log_credentials


class PrivateUrlLogReferenceTests(unittest.TestCase):
    def test_masks_live_credentials_without_xtream_prefix(self):
        for message in (
            'http://provider.example "GET /private-user/private-password/123?token=secret HTTP/1.1" 302',
            'Request failed: https://provider.example/prefix/private-user/private-password/123',
        ):
            result = redact_log_credentials(message)
            for private in ('provider.example', 'private-user', 'private-password', 'secret'):
                self.assertNotIn(private, result)
            self.assertIn('/<path>', result)

    def test_masks_network_endpoints_and_keeps_request_diagnostics(self):
        messages = [
            "Starting new HTTP connection (1): provider.example:8080",
            'http://192.0.2.10:80 "GET /live/user/secret/123 HTTP/1.1" 302 538',
            "HTTPSConnectionPool(host='provider.example', port=8443): failure",
            "Failed to resolve 'provider.example'",
            "https://[2001:db8::1]:443/player_api.php?action=get_live_streams",
        ]
        for message in messages:
            with self.subTest(message=message):
                result = redact_log_credentials(message)
                for private in ("provider.example", "192.0.2.10", "2001:db8::1", "8080", "8443", "secret"):
                    self.assertNotIn(private, result)
                self.assertIn("<server>", result)
        self.assertIn("HTTP/1.1\" 302 538", redact_log_credentials(messages[1]))
        self.assertIn("action=get_live_streams", redact_log_credentials(messages[4]))

    def test_masks_account_and_local_user_identifiers(self):
        message = (
            "Active account changed: name='Private account'; id=abcdef; "
            "account_id=abcdef /home/alice/Downloads/log "
            "C:\\Users\\Alice\\Downloads\\log /Users/alice/log"
        )
        result = redact_log_credentials(message)
        for value in ("Private account", "abcdef", "alice", "Alice"):
            self.assertNotIn(value, result)

    def test_masks_formatted_exception_before_writing_log(self):
        from iptv_player.bootstrap import _CredentialRedactionFilter
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.addFilter(_CredentialRedactionFilter())
        logger = logging.Logger("privacy-test")
        logger.addHandler(handler)
        try:
            raise RuntimeError("https://provider.example:8080/live/user/secret/123")
        except RuntimeError:
            logger.exception("Request failed")
        result = output.getvalue()
        self.assertIn("RuntimeError", result)
        self.assertNotIn("provider.example", result)
        self.assertNotIn("secret", result)

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

