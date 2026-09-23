import unittest
from unittest.mock import Mock

from iptv_player.updater import (
    ReleaseInfo,
    fetch_latest_release,
    is_newer_version,
    version_components,
)


class UpdateCheckerTests(unittest.TestCase):
    def test_extracts_numeric_version_components(self):
        self.assertEqual(version_components("V2.01.17"), (2, 1, 17))

    def test_compares_versions_with_different_component_widths(self):
        self.assertFalse(is_newer_version("V3.0", "V3.0.0"))
        self.assertTrue(is_newer_version("V3.1", "V3.0.9"))
        self.assertFalse(is_newer_version("V2.9.9", "V3.0.0"))

    def test_stable_release_replaces_same_version_beta(self):
        self.assertTrue(is_newer_version("V3.1.0", "V3.1.0-beta"))
        self.assertFalse(is_newer_version("V3.1.0-beta", "V3.1.0"))
        self.assertFalse(is_newer_version("V3.1.0-beta", "V3.1.0-beta"))

    def test_newer_beta_is_offered_to_beta_users(self):
        self.assertTrue(is_newer_version("V3.1.1-beta", "V3.1.0-beta"))

    def test_fetches_latest_release_with_bounded_timeouts(self):
        response = Mock()
        response.json.return_value = [{
            "tag_name": "V3.1.0",
            "html_url": "https://github.com/example/releases/tag/V3.1.0",
            "draft": False,
            "prerelease": False,
        }]
        request_get = Mock(return_value=response)

        release = fetch_latest_release(
            "example/project", 3, "V3.0.0", request_get=request_get
        )

        self.assertEqual(
            release,
            ReleaseInfo(
                version="V3.1.0",
                download_page="https://github.com/example/releases/tag/V3.1.0",
            ),
        )
        request_get.assert_called_once_with(
            "https://api.github.com/repos/example/project/releases",
            timeout=(3, 5),
        )

    def test_beta_channel_selects_newest_prerelease(self):
        response = Mock()
        response.json.return_value = [
            {
                "tag_name": "V3.1.0",
                "html_url": "https://github.com/example/releases/tag/V3.1.0",
                "draft": False,
                "prerelease": False,
            },
            {
                "tag_name": "V3.1.1-beta",
                "html_url": "https://github.com/example/releases/tag/V3.1.1-beta",
                "draft": False,
                "prerelease": False,
            },
        ]

        request_get = Mock(return_value=response)
        release = fetch_latest_release(
            "example/project", 3, "V3.1.0-beta", request_get=request_get
        )

        self.assertEqual(release.version, "V3.1.1-beta")

    def test_stable_channel_ignores_prereleases(self):
        response = Mock()
        response.json.return_value = [
            {
                "tag_name": "V3.1.1-beta",
                "html_url": "https://github.com/example/releases/tag/V3.1.1-beta",
                "draft": False,
                "prerelease": False,
            },
            {
                "tag_name": "V3.1.0",
                "html_url": "https://github.com/example/releases/tag/V3.1.0",
                "draft": False,
                "prerelease": False,
            },
        ]

        release = fetch_latest_release(
            "example/project", 3, "V3.1.0", request_get=Mock(return_value=response)
        )

        self.assertEqual(release.version, "V3.1.0")


if __name__ == "__main__":
    unittest.main()
