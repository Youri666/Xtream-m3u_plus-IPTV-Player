"""Per-account playback history and resume-position persistence."""

from datetime import datetime, timezone
from pathlib import Path

from iptv_player.storage.json_file import read_json_mapping, write_json_file


HISTORY_SCHEMA_VERSION = 1
HISTORY_TYPES = ("LIVE", "Movies", "Series")


def account_history_file(base_filename, account_id):
    """Return the playback-history filename for one IPTV account."""
    base_path = Path(base_filename)
    return base_path.with_name(
        f"{base_path.stem}.{account_id}{base_path.suffix}"
    )


def load_history(filename):
    """Return validated history entries ordered from newest to oldest."""
    data = read_json_mapping(filename)
    entries = data.get("items", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if _valid_entry(entry)]


def record_history(filename, entry, max_items_per_type):
    """Insert or update one item and retain a bounded history per content type."""
    normalized = _normalize_entry(entry)
    if normalized is None:
        return []
    entries = [
        item for item in load_history(filename)
        if item.get("key") != normalized["key"]
    ]
    entries.insert(0, normalized)
    limit = max(1, min(int(max_items_per_type), 1000))
    counts = {stream_type: 0 for stream_type in HISTORY_TYPES}
    retained = []
    for item in entries:
        stream_type = item["type"]
        if counts[stream_type] >= limit:
            continue
        counts[stream_type] += 1
        retained.append(item)
    write_json_file(filename, {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "items": retained,
    })
    return retained


def clear_history(filename):
    """Remove a history file if it exists."""
    try:
        Path(filename).unlink()
    except FileNotFoundError:
        pass


def repair_misclassified_history(filename, live_ids, movie_ids):
    """Repair rows saved as Series while another Series view remained open."""
    entries = load_history(filename)
    live_ids = {str(value) for value in live_ids}
    movie_ids = {str(value) for value in movie_ids}
    changed = False
    repaired = []
    seen_keys = set()
    for entry in entries:
        item = dict(entry)
        stream_id = str(item.get("stream_id", ""))
        if item.get("type") == "Series" and not item.get("series_id"):
            if stream_id in live_ids:
                item["type"] = "LIVE"
            elif stream_id in movie_ids:
                item["type"] = "Movies"
            if item["type"] != "Series":
                item["key"] = f"{item['type']}:{stream_id}"
                changed = True
        if item.get("key") in seen_keys:
            changed = True
            continue
        seen_keys.add(item.get("key"))
        repaired.append(_normalize_entry(item))
    if changed:
        write_json_file(filename, {
            "schema_version": HISTORY_SCHEMA_VERSION,
            "items": [item for item in repaired if item is not None],
        })
    return [item for item in repaired if item is not None]


def resume_position(entry):
    """Return a useful resume position, excluding starts and completed media."""
    try:
        position_ms = max(0, int(entry.get("position_ms", 0)))
        duration_ms = max(0, int(entry.get("duration_ms", 0)))
    except (AttributeError, TypeError, ValueError):
        return 0
    # Ignore only VLC's initial zero-ish timestamp. Even a short watched segment
    # is meaningful when the user explicitly launches it again from History.
    if position_ms < 1_000 or duration_ms <= 0:
        return 0
    if duration_ms - position_ms <= 30_000 or position_ms >= duration_ms * 0.95:
        return 0
    return position_ms


def _normalize_entry(entry):
    if not isinstance(entry, dict):
        return None
    key = str(entry.get("key", "")).strip()
    stream_type = str(entry.get("type", "")).strip()
    title = str(entry.get("title", "")).strip()
    if not key or stream_type not in HISTORY_TYPES or not title:
        return None
    try:
        position_ms = max(0, int(entry.get("position_ms", 0)))
        duration_ms = max(0, int(entry.get("duration_ms", 0)))
    except (TypeError, ValueError):
        position_ms = 0
        duration_ms = 0
    normalized = {
        "key": key,
        "type": stream_type,
        "title": title,
        "last_viewed": str(entry.get("last_viewed") or _utc_timestamp()),
        "position_ms": position_ms,
        "duration_ms": duration_ms,
        "stream_id": str(entry.get("stream_id", "")),
        "container_extension": str(entry.get("container_extension", "") or ""),
        "source_category_name": str(
            entry.get("source_category_name", "") or ""
        ),
        "source_category_id": str(
            entry.get("source_category_id", "") or ""
        ),
    }
    if stream_type == "Series":
        normalized.update({
            "series_id": str(entry.get("series_id", "") or ""),
            "series_title": str(entry.get("series_title", "") or ""),
            "series_category_id": str(entry.get("series_category_id", "") or ""),
            "season": str(entry.get("season", "") or ""),
        })
    return normalized


def _valid_entry(entry):
    return _normalize_entry(entry) is not None


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
