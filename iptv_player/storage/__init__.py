"""Persistent data storage helpers."""

from .account_data import remove_account_data_files
from .favorites import (
    account_favorites_file,
    create_custom_category,
    delete_custom_category,
    entries_in_custom_category,
    entries_in_favorite_order,
    load_custom_categories,
    migrate_legacy_favorites_file,
    rename_custom_category,
    reorder_custom_category,
    reorder_favorites,
    set_custom_category_membership,
    set_favorite,
)
from .json_file import read_json_mapping, write_json_file
from .history import (
    account_history_file,
    clear_history,
    load_history,
    record_history,
    remove_history_entries,
    remove_history_entry,
    repair_misclassified_history,
    resume_position,
)
from .provider_preferences import (
    load_provider_preferences,
    provider_preferences_file,
    save_provider_preferences,
)

__all__ = (
    "account_favorites_file",
    "account_history_file",
    "clear_history",
    "create_custom_category",
    "delete_custom_category",
    "entries_in_custom_category",
    "entries_in_favorite_order",
    "load_custom_categories",
    "migrate_legacy_favorites_file",
    "load_provider_preferences",
    "load_history",
    "provider_preferences_file",
    "read_json_mapping",
    "remove_account_data_files",
    "record_history",
    "remove_history_entries",
    "remove_history_entry",
    "rename_custom_category",
    "reorder_custom_category",
    "reorder_favorites",
    "repair_misclassified_history",
    "resume_position",
    "set_custom_category_membership",
    "set_favorite",
    "save_provider_preferences",
    "write_json_file",
)
