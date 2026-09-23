"""Read-only TMDB metadata access using a user-provided access token."""

import requests


TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


class TmdbClient:
    """Fetch public TMDB metadata without exposing the access token in URLs."""

    def __init__(self, access_token, timeout, request_get=None):
        self.access_token = str(access_token or "").strip()
        self.timeout = timeout
        self.request_get = request_get or requests.get

    def test_connection(self):
        """Validate the token against a lightweight authenticated endpoint."""
        self._get("configuration")

    def details(self, media_type, tmdb_id):
        """Return normalized movie or television metadata."""
        if media_type not in ("movie", "tv"):
            raise ValueError("Unsupported TMDB media type")
        data = self._get(
            f"{media_type}/{tmdb_id}",
            params={"language": "en-US", "append_to_response": "credits,videos"},
        )
        return normalize_tmdb_details(media_type, data)

    def _get(self, endpoint, params=None):
        if not self.access_token:
            raise ValueError("TMDB access token is empty")
        response = self.request_get(
            f"{TMDB_API_BASE}/{endpoint}",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "accept": "application/json",
            },
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("TMDB returned invalid metadata")
        return data


def normalize_tmdb_details(media_type, data):
    """Map TMDB movie and television responses to the existing information UI."""
    credits = data.get("credits") if isinstance(data.get("credits"), dict) else {}
    crew = credits.get("crew") if isinstance(credits.get("crew"), list) else []
    cast = credits.get("cast") if isinstance(credits.get("cast"), list) else []
    director = next(
        (
            person.get("name", "") for person in crew
            if isinstance(person, dict) and person.get("job") == "Director"
        ),
        "",
    )
    if media_type == "tv" and not director:
        creators = data.get("created_by") if isinstance(data.get("created_by"), list) else []
        director = ", ".join(
            creator.get("name", "") for creator in creators
            if isinstance(creator, dict) and creator.get("name")
        )
    videos = data.get("videos") if isinstance(data.get("videos"), dict) else {}
    trailer = next(
        (
            video.get("key", "") for video in videos.get("results", [])
            if isinstance(video, dict)
            and video.get("site") == "YouTube"
            and video.get("type") == "Trailer"
        ),
        "",
    )
    poster_path = data.get("poster_path") or ""
    countries = data.get("production_countries", [])
    return {
        "name": data.get("title") or data.get("name") or "",
        "release_date": data.get("release_date") or data.get("first_air_date") or "",
        "country": ", ".join(
            country.get("name", "") for country in countries
            if isinstance(country, dict) and country.get("name")
        ),
        "genre": ", ".join(
            genre.get("name", "") for genre in data.get("genres", [])
            if isinstance(genre, dict) and genre.get("name")
        ),
        "duration": data.get("runtime") or next(
            iter(data.get("episode_run_time") or []), None
        ),
        "rating": data.get("vote_average"),
        "director": director,
        "cast": ", ".join(
            person.get("name", "") for person in cast[:8]
            if isinstance(person, dict) and person.get("name")
        ),
        "description": data.get("overview") or "",
        "seasons": data.get("number_of_seasons"),
        "poster_url": f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else "",
        "youtube_trailer": trailer,
    }
