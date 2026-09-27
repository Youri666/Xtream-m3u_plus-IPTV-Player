"""Favorite stream persistence and ordering."""

import os
from pathlib import Path
import uuid

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


def load_custom_categories(file_path, stream_type):
    """Return normalized custom categories in their saved display order."""
    data = read_json_mapping(file_path)
    saved_by_type = data.get("custom_categories", {}) or {}
    categories = []
    for category in saved_by_type.get(stream_type, []) or []:
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("id", "")).strip()
        name = str(category.get("name", "")).strip()
        if not category_id or not name:
            continue
        categories.append({
            "id": category_id,
            "name": name,
            "stream_ids": list(dict.fromkeys(
                stream_id for stream_id in category.get("stream_ids", []) or []
                if stream_id is not None
            )),
        })
    return categories


def create_custom_category(file_path, stream_type, name):
    """Create a named custom category and return its stable identifier."""
    clean_name = str(name).strip()
    if not clean_name:
        return None
    data = read_json_mapping(file_path)
    categories = load_custom_categories(file_path, stream_type)
    if any(category["name"].casefold() == clean_name.casefold()
           for category in categories):
        return None
    category_id = uuid.uuid4().hex
    categories.append({"id": category_id, "name": clean_name, "stream_ids": []})
    saved_by_type = data.get("custom_categories", {}) or {}
    saved_by_type[stream_type] = categories
    data["custom_categories"] = saved_by_type
    write_json_file(file_path, data)
    return category_id


def rename_custom_category(file_path, stream_type, category_id, name):
    """Rename one custom category when the new name is unique."""
    clean_name = str(name).strip()
    categories = load_custom_categories(file_path, stream_type)
    if not clean_name or any(
        category["id"] != str(category_id)
        and category["name"].casefold() == clean_name.casefold()
        for category in categories
    ):
        return False
    changed = False
    for category in categories:
        if category["id"] == str(category_id):
            category["name"] = clean_name
            changed = True
            break
    if changed:
        data = read_json_mapping(file_path)
        saved_by_type = data.get("custom_categories", {}) or {}
        saved_by_type[stream_type] = categories
        data["custom_categories"] = saved_by_type
        write_json_file(file_path, data)
    return changed


def delete_custom_category(file_path, stream_type, category_id):
    """Delete one custom category without affecting global favorites."""
    categories = load_custom_categories(file_path, stream_type)
    remaining = [
        category for category in categories
        if category["id"] != str(category_id)
    ]
    if len(remaining) == len(categories):
        return False
    data = read_json_mapping(file_path)
    saved_by_type = data.get("custom_categories", {}) or {}
    saved_by_type[stream_type] = remaining
    data["custom_categories"] = saved_by_type
    write_json_file(file_path, data)
    return True


def set_custom_category_membership(
    file_path, stream_type, category_id, item_ids, enabled
):
    """Add or remove catalog ids while preserving the category's order."""
    categories = load_custom_categories(file_path, stream_type)
    requested = list(dict.fromkeys(
        item_id for item_id in item_ids or [] if item_id is not None
    ))
    requested_set = set(requested)
    changed = False
    for category in categories:
        if category["id"] != str(category_id):
            continue
        current = [
            stream_id for stream_id in category["stream_ids"]
            if stream_id not in requested_set
        ]
        if enabled:
            current.extend(requested)
        changed = current != category["stream_ids"]
        category["stream_ids"] = current
        break
    if changed:
        data = read_json_mapping(file_path)
        saved_by_type = data.get("custom_categories", {}) or {}
        saved_by_type[stream_type] = categories
        data["custom_categories"] = saved_by_type
        write_json_file(file_path, data)
    return changed


def reorder_custom_category(file_path, stream_type, category_id, ordered_ids):
    """Persist the user-defined order of one custom category."""
    categories = load_custom_categories(file_path, stream_type)
    requested = list(dict.fromkeys(
        stream_id for stream_id in ordered_ids or [] if stream_id is not None
    ))
    changed = False
    for category in categories:
        if category["id"] == str(category_id):
            changed = category["stream_ids"] != requested
            category["stream_ids"] = requested
            break
    if changed:
        data = read_json_mapping(file_path)
        saved_by_type = data.get("custom_categories", {}) or {}
        saved_by_type[stream_type] = categories
        data["custom_categories"] = saved_by_type
        write_json_file(file_path, data)
    return changed


def entries_in_custom_category(file_path, stream_type, category_id, entries):
    """Return catalog entries in the custom category's saved order."""
    category = next((
        item for item in load_custom_categories(file_path, stream_type)
        if item["id"] == str(category_id)
    ), None)
    if category is None:
        return []
    id_field = "series_id" if stream_type == "Series" else "stream_id"
    entries_by_id = {entry.get(id_field): entry for entry in entries or []}
    return [
        entries_by_id[stream_id] for stream_id in category["stream_ids"]
        if stream_id in entries_by_id
    ]


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
