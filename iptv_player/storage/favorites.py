"""Favorite stream persistence and ordering."""

import os
from pathlib import Path

from iptv_player.storage.json_file import read_json_mapping, write_json_file


def account_favorites_file(base_filename, account_key):
    """Return the dedicated favorites filename for one provider account."""
    base_path = Path(base_filename)
    return base_path.with_name(
        f"{base_path.stem}.{account_key}{base_path.suffix}"
    )


def migrate_legacy_favorites_file(legacy_filename, dedicated_filename):
    """Move legacy favorites once and return the safe file to use."""
    legacy_path = Path(legacy_filename)
    dedicated_path = Path(dedicated_filename)
    if dedicated_path.is_file() or not legacy_path.is_file():
        return dedicated_path
    try:
        dedicated_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(legacy_path, dedicated_path)
        return dedicated_path
    except OSError:
        # Favorites cannot be downloaded again, so retain the legacy file when
        # migration is not possible instead of silently starting with an empty set.
        return legacy_path


def set_favorite(file_path, stream_type, stream_id, enabled):
    """Add or remove an ID while preserving the user's favorite order."""
    data = read_json_mapping(file_path)
    key = _favorite_key(stream_type)
    ordered_ids = [item_id for item_id in (data.get(key) or []) if item_id != stream_id]
    if enabled:
        ordered_ids.append(stream_id)
    data[key] = ordered_ids
    write_json_file(file_path, data)


def reorder_favorites(file_path, stream_type, ordered_ids):
    """Persist a user-defined order without disturbing other content types."""
    data = read_json_mapping(file_path)
    key = _favorite_key(stream_type)
    requested = list(dict.fromkeys(ordered_ids or []))

    if stream_type == "Series":
        data[key] = requested
    else:
        # LIVE and Movies historically share stream_ids. Replace only the IDs
        # visible in the reordered list so the other content type keeps its slots.
        requested_set = set(requested)
        replacements = iter(requested)
        merged = []
        for item_id in data.get(key, []) or []:
            if item_id in requested_set:
                merged.append(next(replacements, item_id))
            else:
                merged.append(item_id)
        merged.extend(replacements)
        data[key] = merged

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
