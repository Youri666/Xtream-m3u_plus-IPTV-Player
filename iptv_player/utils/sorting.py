"""Pure ordering helpers shared by catalog views."""

import math

from iptv_player.utils.search import normalize_search_text


def provider_rating(entry):
    """Read catalogue ratings only, normalizing the five-point fallback to ten."""
    for field, scale in (("rating", 1), ("rating_5based", 2)):
        value = entry.get(field)
        if isinstance(value, bool):
            continue
        try:
            rating = float(str(value).strip().replace(",", ".")) * scale
        except (TypeError, ValueError):
            continue
        if math.isfinite(rating) and 0 < rating <= 10:
            return rating
    return None


def ordered_catalog_entries(
    entries, sorting_enabled, descending=False, title_key="name", rating_order=None
):
    """Return a stable copy ordered by title or provider rating."""
    ordered = list(entries)
    if sorting_enabled:
        if rating_order in (2, 3):
            def rating_key(entry):
                rating = provider_rating(entry)
                return (rating is None, (-rating if rating_order == 2 else rating)
                        if rating is not None else 0)
            ordered.sort(key=rating_key)
            return ordered
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
