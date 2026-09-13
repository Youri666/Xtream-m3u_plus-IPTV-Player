"""Transform provider catalog entries into application-ready records."""


def normalized_stream_type(stream_type):
    """Normalize the broad stream type labels returned by providers."""
    if "live" in stream_type:
        return "live"
    if "movie" in stream_type:
        return "movie"
    return stream_type


def prepare_catalog_entries(entries_per_stream_type, favorites, url_builder):
    """Attach playable URLs and favorite state to downloaded catalog entries."""
    favorite_stream_ids = set(favorites.get("stream_ids", []))
    favorite_series_ids = set(favorites.get("series_ids", []))

    for entries in entries_per_stream_type.values():
        for entry in entries:
            stream_type = normalized_stream_type(
                entry.get("stream_type", "series")
            )
            stream_id = entry.get("stream_id", -1)
            series_id = entry.get("series_id", -1)
            container_extension = entry.get("container_extension", "m3u8")

            if stream_id:
                entry["url"] = url_builder(
                    stream_type, stream_id, container_extension
                )
                entry["favorite"] = stream_id in favorite_stream_ids
            else:
                entry["url"] = None

            if stream_type == "series":
                entry["stream_type"] = stream_type
                if series_id:
                    entry["favorite"] = series_id in favorite_series_ids

    return entries_per_stream_type

