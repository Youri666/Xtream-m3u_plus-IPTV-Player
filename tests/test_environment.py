import os
import unittest
from unittest.mock import patch

from iptv_player.utils.environment import (
    bounded_float_environment,
    bounded_integer_environment,
)


class PlayerProcessEnvironmentTests(unittest.TestCase):
    def test_integer_environment_is_clamped_and_rejects_invalid_text(self):
        with patch.dict(os.environ, {"PLAYER_TEST_VALUE": "500"}):
            self.assertEqual(
                bounded_integer_environment("PLAYER_TEST_VALUE", 10, 1, 300),
                300,
            )

        with patch.dict(os.environ, {"PLAYER_TEST_VALUE": "invalid"}):
            self.assertEqual(
                bounded_integer_environment("PLAYER_TEST_VALUE", 10, 1, 300),
                10,
            )

    def test_float_environment_is_clamped_and_rejects_invalid_text(self):
        with patch.dict(os.environ, {"PLAYER_TEST_VALUE": "0.01"}):
            self.assertEqual(
                bounded_float_environment("PLAYER_TEST_VALUE", 0.25, 0.05, 1.0),
                0.05,
            )

        with patch.dict(os.environ, {"PLAYER_TEST_VALUE": "invalid"}):
            self.assertEqual(
                bounded_float_environment("PLAYER_TEST_VALUE", 0.25, 0.05, 1.0),
                0.25,
            )


if __name__ == "__main__":
    unittest.main()
