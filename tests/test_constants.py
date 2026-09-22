import unittest

from iptv_player.constants import (
    CURRENT_VERSION,
    DEFAULT_INTERNAL_SEEK_STEP_SECONDS,
    DEFAULT_INTERNAL_SPEED_STEP,
    DEFAULT_INTERNAL_VOLUME_STEP_PERCENT,
    DEFAULT_URL_FORMATS,
)


class ApplicationDefaultsTests(unittest.TestCase):
    def test_version_uses_release_tag_format(self):
        self.assertRegex(
            CURRENT_VERSION,
            r"^V\d+\.\d+\.\d+(?:-(?:alpha|beta|rc))?$",
        )

    def test_internal_player_defaults_remain_bounded(self):
        self.assertGreater(DEFAULT_INTERNAL_SEEK_STEP_SECONDS, 0)
        self.assertGreater(DEFAULT_INTERNAL_VOLUME_STEP_PERCENT, 0)
        self.assertLessEqual(DEFAULT_INTERNAL_VOLUME_STEP_PERCENT, 100)
        self.assertGreater(DEFAULT_INTERNAL_SPEED_STEP, 0)

    def test_default_urls_keep_required_placeholders(self):
        required = {"server", "username", "password", "stream_id", "container_extension"}
        for url_format in DEFAULT_URL_FORMATS.values():
            for placeholder in required:
                self.assertIn("{" + placeholder + "}", url_format)


if __name__ == "__main__":
    unittest.main()

