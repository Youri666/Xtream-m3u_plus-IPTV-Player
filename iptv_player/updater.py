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


def is_newer_version(candidate, current):
    """Return whether a candidate tag represents a newer application version."""
    candidate_parts = version_components(candidate)
    current_parts = version_components(current)
    width = max(len(candidate_parts), len(current_parts))
    candidate_parts += (0,) * (width - len(candidate_parts))
    current_parts += (0,) * (width - len(current_parts))
    return candidate_parts > current_parts


def fetch_latest_release(repository, connection_timeout, request_get=None):
    """Fetch the latest GitHub release metadata for a repository."""
    request_get = request_get or requests.get
    api_url = f"https://api.github.com/repos/{repository}/releases/latest"
    response = request_get(api_url, timeout=(connection_timeout, 5))
    data = response.json()
    return ReleaseInfo(
        version=data["tag_name"],
        download_page=data["html_url"],
    )
