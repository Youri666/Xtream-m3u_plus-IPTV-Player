import base64
import unittest
from datetime import datetime

from iptv_player.provider.epg import (
    apply_epg_offset,
    decode_epg_data,
    decode_epg_text,
)


class EpgDecodingTests(unittest.TestCase):
    def test_decodes_utf8_and_windows_1256(self):
        self.assertEqual(decode_epg_text("Café".encode("utf-8")), "Café")
        arabic = "مرحبا"
        self.assertEqual(decode_epg_text(arabic.encode("cp1256")), arabic)

    def test_converts_provider_listing(self):
        start = 1_700_000_000
        stop = start + 3_600
        payload = {
            "epg_listings": [
                {
                    "start_timestamp": str(start),
                    "stop_timestamp": str(stop),
                    "title": base64.b64encode("Evening News".encode()).decode(),
                    "description": base64.b64encode("Headlines".encode()).decode(),
                }
            ]
        }

        result = decode_epg_data(payload)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["program_name"], "Evening News")
        self.assertEqual(result[0]["description"], "Headlines")
        self.assertEqual(result[0]["start_time"], datetime.fromtimestamp(start))
        self.assertEqual(result[0]["stop_time"], datetime.fromtimestamp(stop))
        self.assertEqual(
            result[0]["date"], datetime.fromtimestamp(start).strftime("%d-%m-%Y")
        )

    def test_applies_offset_without_mutating_decoded_listing(self):
        entry = {
            "start_time": datetime(2026, 9, 21, 23, 30),
            "stop_time": datetime(2026, 9, 22, 0, 30),
            "program_name": "Late News",
            "description": "Headlines",
            "date": "21-09-2026",
        }

        result = apply_epg_offset([entry], 90)

        self.assertEqual(result[0]["start_time"], datetime(2026, 9, 22, 1, 0))
        self.assertEqual(result[0]["stop_time"], datetime(2026, 9, 22, 2, 0))
        self.assertEqual(result[0]["date"], "22-09-2026")
        self.assertEqual(entry["start_time"], datetime(2026, 9, 21, 23, 30))


if __name__ == "__main__":
    unittest.main()

