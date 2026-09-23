"""Helpers for exporting direct VOD download links."""

import re


def flatten_series_episodes(episodes_by_season):
    """Return every episode in natural season order and provider episode order."""
    if not isinstance(episodes_by_season, dict):
        return []

    def season_key(value):
        try:
            return 0, int(value)
        except (TypeError, ValueError):
            return 1, str(value).casefold()

    episodes = []
    for season in sorted(episodes_by_season, key=season_key):
        season_episodes = episodes_by_season.get(season, [])
        if isinstance(season_episodes, list):
            for episode in season_episodes:
                if isinstance(episode, dict):
                    exported_episode = dict(episode)
                    exported_episode["_export_season"] = season
                    episodes.append(exported_episode)
    return episodes


def safe_download_filename(title, fallback="download-links"):
    """Create a portable text filename from a provider title."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(title or "")).strip()
    cleaned = cleaned.rstrip(". ")
    return f"{cleaned or fallback}.txt"


def download_link_text(urls):
    """Serialize valid URLs as one link per line."""
    return "\n".join(str(url).strip() for url in urls if str(url).strip())


def structured_download_text(title, records):
    """Format named VOD links as a readable movie, episode, or series document."""
    lines = [str(title or "Download links").strip(), ""]
    current_season = None
    season_episode_index = 0
    for record in records:
        url = str(record.get("url", "")).strip()
        if not url:
            continue
        season = record.get("season")
        if season != current_season and season not in (None, ""):
            if current_season is not None and lines[-1] != "":
                lines.append("")
            lines.extend([_season_label(season), ""])
            current_season = season
            season_episode_index = 0

        season_episode_index += 1
        episode_number = record.get("episode_number") or season_episode_index
        episode_title = str(record.get("title", "")).strip()
        if season not in (None, ""):
            label = f"Episode {_number_label(episode_number)}"
            if episode_title:
                label += f" - {episode_title}"
            lines.extend([label, url, ""])
        elif episode_title and episode_title != str(title or "").strip():
            lines.extend([episode_title, url, ""])
        else:
            lines.extend([url, ""])
    return "\n".join(lines).rstrip() + "\n"


def _season_label(season):
    """Return a readable season heading with padded numeric values."""
    text = str(season).strip().removeprefix("Season ").strip()
    return f"Season {_number_label(text)}"


def _number_label(value):
    """Pad numeric season and episode labels while preserving provider text."""
    try:
        return f"{int(value):02d}"
    except (TypeError, ValueError):
        return str(value)
