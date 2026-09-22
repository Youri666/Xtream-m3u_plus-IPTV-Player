"""Decode provider EPG payloads independently from Qt workers."""

import base64
from datetime import datetime, timedelta


EPG_TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp1256", "iso-8859-6", "cp1252")


def decode_epg_text(raw_bytes):
    """Decode provider text using common EPG encodings in priority order."""
    for encoding in EPG_TEXT_ENCODINGS:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def decode_epg_data(epg_data):
    """Convert encoded Xtream listings into the fields displayed by the UI."""
    decoded_entries = []
    for entry in epg_data["epg_listings"]:
        start_timestamp = datetime.fromtimestamp(int(entry["start_timestamp"]))
        stop_timestamp = datetime.fromtimestamp(int(entry["stop_timestamp"]))
        decoded_entries.append(
            {
                "start_time": start_timestamp,
                "stop_time": stop_timestamp,
                "program_name": decode_epg_text(base64.b64decode(entry["title"])),
                "description": decode_epg_text(
                    base64.b64decode(entry["description"])
                ),
                "date": (
                    f"{start_timestamp.day:02}-{start_timestamp.month:02}-"
                    f"{start_timestamp.year}"
                ),
            }
        )
    return decoded_entries


def apply_epg_offset(epg_entries, offset_minutes):
    """Return listings shifted by one account-specific time offset."""
    offset = timedelta(minutes=max(-720, min(int(offset_minutes), 720)))
    shifted_entries = []
    for entry in epg_entries:
        shifted = dict(entry)
        shifted["start_time"] = entry["start_time"] + offset
        shifted["stop_time"] = entry["stop_time"] + offset
        shifted["date"] = shifted["start_time"].strftime("%d-%m-%Y")
        shifted_entries.append(shifted)
    return shifted_entries

