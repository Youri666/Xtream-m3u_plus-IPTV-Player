"""Ordered migrations for persisted IPTV Player settings."""

import configparser
import os
import uuid
from os import path

from iptv_player.config.ini import write_config_file


def migrate_user_data_file(file_path, default_url_formats, current_schema_version):
    """Upgrade a user configuration without changing established preferences."""
    legacy_account_names = _read_legacy_account_names(file_path)
    config = configparser.ConfigParser()
    try:
        config.read(file_path)
    except (configparser.Error, UnicodeDecodeError) as error:
        print(f"User data file is corrupt, ignoring it: {error}")
        try:
            os.rename(file_path, file_path + ".bak")
        except OSError:
            pass
        return

    _append_missing_url_formats(config, default_url_formats)

    try:
        stored_schema_version = config.getint(
            "Application", "config_schema_version", fallback=0
        )
    except (ValueError, configparser.Error):
        stored_schema_version = 0

    if stored_schema_version < 1:
        _migrate_content_switches(config)

    if stored_schema_version < 2:
        _migrate_accounts_to_stable_ids(config, legacy_account_names)

    if "Application" not in config:
        config["Application"] = {}
    config.remove_option("Application", "last_run_version")
    config["Application"]["config_schema_version"] = str(
        max(stored_schema_version, current_schema_version)
    )

    try:
        write_config_file(file_path, config)
    except OSError as error:
        print(f"Could not persist user data file: {error}")


def migrate_legacy_player_volume(user_data_file, data_directory):
    """Move the former standalone volume preference into the main INI file."""
    legacy_path = path.join(data_directory, ".embedded_player_volume")
    if not path.isfile(legacy_path):
        return

    config = configparser.ConfigParser()
    try:
        config.read(user_data_file)
        if not config.has_option("InternalPlayer", "volume"):
            with open(legacy_path, "r", encoding="utf-8") as legacy_file:
                volume = max(0, min(100, int(legacy_file.read().strip())))
            if not config.has_section("InternalPlayer"):
                config.add_section("InternalPlayer")
            config.set("InternalPlayer", "volume", str(volume))
            write_config_file(user_data_file, config)
        os.remove(legacy_path)
    except (OSError, ValueError, configparser.Error, UnicodeDecodeError) as error:
        print(f"Could not migrate the legacy player volume: {error}")


def _append_missing_url_formats(config, default_url_formats):
    if "Credentials" not in config:
        return

    defaults = [
        default_url_formats["live"],
        default_url_formats["movie"],
        default_url_formats["series"],
    ]
    for account_name, data in config["Credentials"].items():
        parts = data.split("|")
        if data.startswith("manual|"):
            required_length = 7
        elif data.startswith("m3u_plus|"):
            required_length = 5
        else:
            continue

        missing = required_length - len(parts)
        if missing > 0:
            parts += defaults[-missing:]
            config["Credentials"][account_name] = "|".join(parts)


def _migrate_content_switches(config):
    try:
        legacy_vods_enabled = config.getboolean("VOD", "enabled", fallback=True)
    except (ValueError, configparser.Error):
        legacy_vods_enabled = True

    if "Content" not in config:
        config["Content"] = {}
    content = config["Content"]
    content.setdefault("LIVE", "True")
    content.setdefault("Movies", str(legacy_vods_enabled))
    content.setdefault("Series", str(legacy_vods_enabled))


def _migrate_accounts_to_stable_ids(config, legacy_account_names):
    """Move user-facing account labels out of INI option keys."""
    if "Credentials" not in config:
        return

    startup_name = config.get(
        "Startup credentials", "startup_credentials", fallback="None"
    )
    startup_account_id = ""
    for parsed_name, serialized_account in list(config["Credentials"].items()):
        stored_name = legacy_account_names.get(parsed_name.casefold(), parsed_name)
        display_name = (
            startup_name
            if stored_name.casefold() == startup_name.casefold()
            else stored_name
        )
        account_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"iptv-player:{stored_name.casefold()}:{serialized_account}",
        ).hex
        section_name = f"Account:{account_id}"
        if section_name not in config:
            config.add_section(section_name)
        config[section_name]["name"] = display_name
        config[section_name]["credentials"] = serialized_account
        if stored_name.casefold() == startup_name.casefold():
            startup_account_id = account_id

    config.remove_section("Credentials")
    if "Startup credentials" not in config:
        config["Startup credentials"] = {}
    config["Startup credentials"].pop("startup_credentials", None)
    config["Startup credentials"]["startup_account_id"] = startup_account_id


def _read_legacy_account_names(file_path):
    """Read legacy credential keys once without ConfigParser lowercasing them."""
    case_preserving_config = configparser.ConfigParser()
    case_preserving_config.optionxform = str
    try:
        case_preserving_config.read(file_path)
    except (configparser.Error, UnicodeDecodeError):
        return {}
    if "Credentials" not in case_preserving_config:
        return {}
    return {
        name.casefold(): name
        for name in case_preserving_config["Credentials"]
    }
