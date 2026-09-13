"""Pure ordering helpers shared by catalog views."""


def ordered_catalog_entries(entries, sorting_enabled, descending=False):
    """Return a copy of catalog entries in the requested title order."""
    ordered = list(entries)
    if sorting_enabled:
        ordered.sort(
            key=lambda entry: entry.get("name", "").casefold(),
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
