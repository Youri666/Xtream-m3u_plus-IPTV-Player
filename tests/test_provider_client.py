import unittest

from iptv_player.provider.client import (
    DEFAULT_USER_AGENT_HEADER,
    XtreamClient,
    provider_headers,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_checked = False

    def raise_for_status(self):
        self.status_checked = True

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.response = FakeResponse(payload)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class ProviderHeadersTests(unittest.TestCase):
    def test_empty_user_agent_uses_default(self):
        self.assertEqual(provider_headers("")["User-Agent"], DEFAULT_USER_AGENT_HEADER)

    def test_custom_user_agent_is_trimmed(self):
        self.assertEqual(provider_headers("  IPTV Test  ")["User-Agent"], "IPTV Test")


class XtreamClientTests(unittest.TestCase):
    def test_builds_authenticated_action_request(self):
        session = FakeSession({"items": []})
        client = XtreamClient(
            "https://provider.example/",
            "viewer",
            "secret",
            user_agent="Test Agent",
            timeout=(4, 20),
            session=session,
        )

        result = client.get_json("get_live_streams", category_id="12")

        self.assertEqual(result, {"items": []})
        self.assertTrue(session.response.status_checked)
        url, options = session.calls[0]
        self.assertEqual(url, "https://provider.example/player_api.php")
        self.assertEqual(
            options["params"],
            {
                "username": "viewer",
                "password": "secret",
                "action": "get_live_streams",
                "category_id": "12",
            },
        )
        self.assertEqual(options["headers"]["User-Agent"], "Test Agent")
        self.assertEqual(options["timeout"], (4, 20))


if __name__ == "__main__":
    unittest.main()

