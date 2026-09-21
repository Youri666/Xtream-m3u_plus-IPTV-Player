import unittest

from iptv_player.provider.network import (
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_LIVE_STATUS_RETRIES,
    DEFAULT_LIVE_STATUS_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    NetworkSettings,
)


class NetworkSettingsTests(unittest.TestCase):
    def test_new_settings_use_network_defaults(self):
        settings = NetworkSettings()

        self.assertEqual(settings.connection_timeout, DEFAULT_CONNECTION_TIMEOUT)
        self.assertEqual(settings.read_timeout, DEFAULT_READ_TIMEOUT)
        self.assertEqual(settings.live_status_timeout, DEFAULT_LIVE_STATUS_TIMEOUT)
        self.assertEqual(settings.live_status_retries, DEFAULT_LIVE_STATUS_RETRIES)

    def test_settings_instances_do_not_share_mutable_state(self):
        first = NetworkSettings()
        second = NetworkSettings()

        first.connection_timeout = 99

        self.assertEqual(second.connection_timeout, DEFAULT_CONNECTION_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
