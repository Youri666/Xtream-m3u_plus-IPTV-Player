"""Build playable stream URLs from provider entries and account settings."""


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

