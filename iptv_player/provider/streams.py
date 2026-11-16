"""Build playable stream URLs from provider entries and account settings."""

import logging
from time import monotonic

from requests import RequestException


def detect_live_url_format(client, server, formats):
    """Confirm a preset using a small sample of a provider's live streams."""
    streams = client.get_json("get_live_streams")
    if not isinstance(streams, list):
        logging.debug("Live URL test: provider returned a non-list channel response")
        return None
    stream_ids = []
    for entry in streams:
        stream_id = entry.get("stream_id") if isinstance(entry, dict) else None
        if str(stream_id).isdigit() and stream_id not in stream_ids:
            stream_ids.append(stream_id)
            if len(stream_ids) == 2:
                break

    logging.debug("Live URL test: %d channels, %d candidate formats", len(stream_ids), len(formats))
    deadline = monotonic() + 15
    for channel_number, stream_id in enumerate(stream_ids, 1):
        for format_number, template in enumerate(formats, 1):
            remaining = deadline - monotonic()
            if remaining <= 0:
                logging.debug("Live URL test: attempt budget exhausted")
                return None
            timeout = min(2, remaining)
            started = monotonic()
            status = None
            redirects = None
            phase = "build-url"
            try:
                url = generate_stream_url(
                    server.rstrip("/"), client.username, client.password,
                    "live", stream_id, "", template, "",
                )
                phase = "open-stream"
                with client.session.get(
                    url, headers=client.headers, stream=True, timeout=timeout,
                ) as response:
                    status = response.status_code
                    redirects = len(response.history)
                    phase = "check-http-status"
                    response.raise_for_status()
                    phase = "read-first-block"
                    sample = next(response.iter_content(chunk_size=512), b"")
                    hls = sample.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"#EXTM3U") and b"#EXT-X-" in sample
                    mpeg_ts = len(sample) > 376 and sample[0] == sample[188] == sample[376] == 0x47
                    logging.debug(
                        "Live URL test: channel=%d candidate=%d HTTP=%s redirects=%d "
                        "bytes=%d HLS=%s MPEG-TS=%s elapsed=%.2fs",
                        channel_number, format_number, status, len(response.history),
                        len(sample), hls, mpeg_ts, monotonic() - started,
                    )
                    if logging.getLogger().isEnabledFor(logging.DEBUG):
                        # Log only derived facts. Headers and payloads may contain secrets.
                        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                        known_types = (
                            "video/mp2t", "application/vnd.apple.mpegurl", "application/x-mpegurl",
                            "application/octet-stream", "text/html", "text/plain", "application/json",
                        )
                        prefix = sample.removeprefix(b"\xef\xbb\xbf").lstrip()
                        ts_offset = next(
                            (i for i in range(len(sample) - 376)
                             if sample[i] == sample[i + 188] == sample[i + 376] == 0x47),
                            None,
                        )
                        # Some transport streams use 192- or 204-byte packets.
                        ts_packet_sizes = [
                            size for size in (188, 192, 204)
                            if any(
                                sample[i] == sample[i + size] == sample[i + 2 * size] == 0x47
                                for i in range(min(size, len(sample) - 2 * size))
                            )
                        ]
                        logging.debug(
                            "Live URL test: channel=%d candidate=%d content-type=%s "
                            "EXTM3U=%s EXT-X=%s HTML-like=%s JSON-like=%s TS-sync-offset=%s "
                            "TS-packet-sizes=%s result=%s",
                            channel_number, format_number,
                            content_type if content_type in known_types else "missing" if not content_type else "other",
                            prefix.startswith(b"#EXTM3U"), b"#EXT-X-" in sample,
                            prefix.startswith(b"<"), prefix.startswith((b"{", b"[")), ts_offset,
                            ts_packet_sizes,
                            "confirmed" if hls or mpeg_ts else "unrecognized" if sample else "empty",
                        )
                    if hls or mpeg_ts:
                        logging.debug(
                            "Live URL test: confirmed candidate=%d on channel=%d",
                            format_number, channel_number,
                        )
                        return template
            except (RequestException, ValueError, KeyError, IndexError, AttributeError) as error:
                # Exception messages and response data can contain credentials.
                logging.debug(
                    "Live URL test: channel=%d candidate=%d phase=%s HTTP=%s redirects=%s "
                    "timeout=%.2fs error=%s elapsed=%.2fs",
                    channel_number, format_number, phase, status, redirects,
                    timeout, type(error).__name__, monotonic() - started,
                )
                continue
    logging.debug("Live URL test: no candidate confirmed")
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

