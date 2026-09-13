"""Favorite stream persistence and ordering."""

from iptv_player.storage.json_file import read_json_mapping, write_json_file


def set_favorite(file_path, stream_type, stream_id, enabled):
    """Add or remove an ID while preserving the user's favorite order."""
    data = read_json_mapping(file_path)
    key = _favorite_key(stream_type)
    ordered_ids = [item_id for item_id in (data.get(key) or []) if item_id != stream_id]
    if enabled:
        ordered_ids.append(stream_id)
    data[key] = ordered_ids
    write_json_file(file_path, data)


def entries_in_favorite_order(file_path, stream_type, entries):
    """Return favorite entries in saved order, with a catalog-order fallback."""
    entries = list(entries or [])
    id_field = "series_id" if stream_type == "Series" else "stream_id"
    ordered_ids = read_json_mapping(file_path).get(_favorite_key(stream_type), []) or []
    if not ordered_ids:
        return [entry for entry in entries if entry.get("favorite")]

    entries_by_id = {entry.get(id_field): entry for entry in entries}
    return [entries_by_id[item_id] for item_id in ordered_ids if item_id in entries_by_id]


def _favorite_key(stream_type):
    return "series_ids" if stream_type == "Series" else "stream_ids"
