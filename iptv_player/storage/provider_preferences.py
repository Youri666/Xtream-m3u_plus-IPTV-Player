"""Per-account category preference persistence."""

from pathlib import Path

from iptv_player.storage.json_file import read_json_mapping, write_json_file


def provider_preferences_file(base_filename, account_id):
    """Return the category-preference filename for one IPTV account."""
    base_path = Path(base_filename)
    return base_path.with_name(
        f"{base_path.stem}.{account_id}{base_path.suffix}"
    )


def load_provider_preferences(filename):
    """Return validated category preferences with safe empty defaults."""
    data = read_json_mapping(filename)
    hidden_categories = data.get("hidden_categories", {})
    category_sorting = data.get("category_sorting", {})
    content_enabled = data.get("content_enabled", {})
    return {
        "hidden_categories": (
            hidden_categories if isinstance(hidden_categories, dict) else {}
        ),
        "category_sorting": (
            category_sorting if isinstance(category_sorting, dict) else {}
        ),
        "content_enabled": (
            content_enabled if isinstance(content_enabled, dict) else {}
        ),
    }


def save_provider_preferences(
    filename, hidden_categories, category_sorting, content_enabled=None
):
    """Atomically persist all category preferences for one IPTV account."""
    write_json_file(filename, {
        "hidden_categories": hidden_categories,
        "category_sorting": category_sorting,
        "content_enabled": content_enabled or {},
    })
