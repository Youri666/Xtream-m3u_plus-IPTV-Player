"""Pure ordering helpers shared by catalog views."""

from iptv_player.utils.search import normalize_search_text


def ordered_catalog_entries(
    entries, sorting_enabled, descending=False, title_key="name"
):
    """Return a copy of catalog entries in the requested title order."""
    ordered = list(entries)
    if sorting_enabled:
        ordered.sort(
            key=lambda entry: normalize_search_text(entry.get(title_key, "")),
            reverse=descending,
        )
    return ordered


def ordered_season_keys(seasons, descending=False):
    """Order numeric seasons naturally and place named seasons afterwards."""
    def season_sort_key(key):
        try:
            return 0, int(key)
        except (TypeError, ValueError):
            return 1, str(key).casefold()

    return sorted(seasons, key=season_sort_key, reverse=descending)
