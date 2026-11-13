"""Build playable stream URLs from provider entries and account settings."""

from time import monotonic

from requests import RequestException


def detect_live_url_format(client, server, formats):
    """Confirm a preset using a small sample of a provider's live streams."""
    streams = client.get_json("get_live_streams")
    if not isinstance(streams, list):
        return None
    stream_ids = []
    for entry in streams:
        stream_id = entry.get("stream_id") if isinstance(entry, dict) else None
        if str(stream_id).isdigit() and stream_id not in stream_ids:
            stream_ids.append(stream_id)
            if len(stream_ids) == 2:
                break

    deadline = monotonic() + 15
    for stream_id in stream_ids:
        for template in formats:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return None
            timeout = min(2, remaining)
            try:
                url = generate_stream_url(
                    server.rstrip("/"), client.username, client.password,
                    "live", stream_id, "", template, "",
                )
                with client.session.get(
                    url, headers=client.headers, stream=True, timeout=timeout,
                ) as response:
                    response.raise_for_status()
                    sample = next(response.iter_content(chunk_size=512), b"")
                    if sample.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"#EXTM3U") and b"#EXT-X-" in sample:
                        return template
                    if len(sample) > 376 and sample[0] == sample[188] == sample[376] == 0x47:
                        return template
            except (RequestException, ValueError, KeyError, IndexError, AttributeError):
                continue
    return None


def generate_stream_url(
    server,
    username,
    password,
    stream_type,
    stream_id,
    container_extension,
    live_url_format,
    movie_url_format,
):
    """Format a playable URL while respecting customized provider templates."""
    if stream_type == "live":
        url_format = live_url_format
    elif stream_type == "movie":
        url_format = movie_url_format
    else:
        url_format = (
            "{server}/{stream_type}/{username}/{password}/"
            "{stream_id}.{container_extension}"
        )

    extension = container_extension
    if ".{container_extension}" not in url_format:
        extension = ""

    return url_format.format(
        server=server,
        username=username,
        password=password,
        stream_type=stream_type,
        stream_id=stream_id,
        container_extension=extension,
    )

