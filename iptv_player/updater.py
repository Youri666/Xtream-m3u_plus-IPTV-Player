"""GitHub release lookup and application version comparison."""

from dataclasses import dataclass
import re

import requests


@dataclass(frozen=True)
class ReleaseInfo:
    """Describe the latest published application release."""

    version: str
    download_page: str


def version_components(version):
    """Return the numeric components from a release tag."""
    return tuple(int(component) for component in re.findall(r"\d+", version or ""))


def is_prerelease_version(version):
    """Return whether a release tag contains a prerelease suffix."""
    return bool(re.search(r"\d(?:[-_.]?(?:alpha|beta|rc))", version or "", re.I))


def is_newer_version(candidate, current):
    """Return whether a candidate tag represents a newer application version."""
    candidate_parts = version_components(candidate)
    current_parts = version_components(current)
    width = max(len(candidate_parts), len(current_parts))
    candidate_parts += (0,) * (width - len(candidate_parts))
    current_parts += (0,) * (width - len(current_parts))
    if candidate_parts != current_parts:
        return candidate_parts > current_parts
    return is_prerelease_version(current) and not is_prerelease_version(candidate)


def _version_sort_key(version):
    """Sort releases numerically, preferring stable at an equal version."""
    return version_components(version), not is_prerelease_version(version)


def fetch_latest_release(
    repository, connection_timeout, current_version="", request_get=None
):
    """Fetch the newest release available to the current release channel."""
    request_get = request_get or requests.get
    api_url = f"https://api.github.com/repos/{repository}/releases"
    response = request_get(api_url, timeout=(connection_timeout, 5))
    releases = response.json()
    if not isinstance(releases, list):
        raise ValueError("GitHub returned invalid release metadata")

    accepts_prereleases = is_prerelease_version(current_version)
    eligible = [
        release for release in releases
        if isinstance(release, dict)
        and not release.get("draft", False)
        and (
            accepts_prereleases
            or not (
                release.get("prerelease", False)
                or is_prerelease_version(release.get("tag_name", ""))
            )
        )
        and release.get("tag_name")
        and release.get("html_url")
    ]
    if not eligible:
        raise ValueError("No eligible GitHub release was found")
    data = max(eligible, key=lambda release: _version_sort_key(release["tag_name"]))
    return ReleaseInfo(
        version=data["tag_name"],
        download_page=data["html_url"],
    )
