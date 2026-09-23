"""Persistence and validation for the Advanced settings dialog."""

import configparser
from dataclasses import dataclass

from iptv_player.config.ini import read_config_file, write_config_file
from iptv_player.constants import DEFAULT_HISTORY_SIZE
from iptv_player.provider.client import DEFAULT_USER_AGENT_HEADER
from iptv_player.provider.network import (
    DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL,
    DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_LIVE_STATUS_RETRIES,
    DEFAULT_LIVE_STATUS_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    MAX_LIVE_STATUS_RETRIES,
)


@dataclass(frozen=True)
class AdvancedPreferences:
    """Hold one complete, validated snapshot of advanced preferences."""

    user_agent: str = DEFAULT_USER_AGENT_HEADER
    connection_timeout: int = DEFAULT_CONNECTION_TIMEOUT
    read_timeout: int = DEFAULT_READ_TIMEOUT
    live_status_timeout: int = DEFAULT_LIVE_STATUS_TIMEOUT
    live_status_retries: int = DEFAULT_LIVE_STATUS_RETRIES
    stream_status_enabled: bool = True
    account_refresh_interval: int = DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL
    account_auto_refresh_enabled: bool = True
    catalog_cache_enabled: bool = True
    catalog_cache_max_age_hours: int = DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS
    detailed_logging_enabled: bool = False
    history_size: int = DEFAULT_HISTORY_SIZE
    tmdb_read_access_token: str = ""


def load_advanced_preferences(filename):
    """Load advanced preferences while isolating malformed values."""
    try:
        config = read_config_file(filename)
    except (configparser.Error, UnicodeDecodeError):
        config = configparser.ConfigParser()

    return AdvancedPreferences(
        user_agent=config.get(
            "User-Agent", "user-agent", fallback=DEFAULT_USER_AGENT_HEADER
        ) or DEFAULT_USER_AGENT_HEADER,
        connection_timeout=_bounded_int(
            config, "Timeouts", "CONNECTION_TIMEOUT",
            DEFAULT_CONNECTION_TIMEOUT, 1, 999,
        ),
        read_timeout=_bounded_int(
            config, "Timeouts", "READ_TIMEOUT", DEFAULT_READ_TIMEOUT, 1, 999,
        ),
        live_status_timeout=_bounded_int(
            config, "Timeouts", "LIVE_STATUS_TIMEOUT",
            DEFAULT_LIVE_STATUS_TIMEOUT, 1, 999,
        ),
        live_status_retries=_bounded_int(
            config, "Timeouts", "LIVE_STATUS_RETRIES",
            DEFAULT_LIVE_STATUS_RETRIES, 0, MAX_LIVE_STATUS_RETRIES,
        ),
        stream_status_enabled=_boolean(
            config, "StreamStatus", "enabled", True
        ),
        account_refresh_interval=_bounded_int(
            config, "AccountInfo", "refresh_interval",
            DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL, 10, 3600,
        ),
        account_auto_refresh_enabled=_boolean(
            config, "AccountInfo", "auto_refresh_enabled", True
        ),
        catalog_cache_enabled=_boolean(
            config, "CatalogCache", "enabled", True
        ),
        catalog_cache_max_age_hours=_bounded_int(
            config, "CatalogCache", "max_age_hours",
            DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS, 1, 720,
        ),
        detailed_logging_enabled=_boolean(
            config, "Logging", "detailed", False
        ),
        history_size=_bounded_int(
            config, "History", "max_items_per_type", DEFAULT_HISTORY_SIZE, 1, 1000
        ),
        tmdb_read_access_token=config.get(
            "TMDB", "read_access_token", fallback=""
        ).strip(),
    )


def save_advanced_preferences(filename, preferences):
    """Persist one complete advanced-preference snapshot atomically."""
    try:
        config = read_config_file(filename)
    except (configparser.Error, UnicodeDecodeError):
        config = configparser.ConfigParser()

    config["User-Agent"] = {"user-agent": preferences.user_agent}
    config["Timeouts"] = {
        "CONNECTION_TIMEOUT": str(preferences.connection_timeout),
        "READ_TIMEOUT": str(preferences.read_timeout),
        "LIVE_STATUS_TIMEOUT": str(preferences.live_status_timeout),
        "LIVE_STATUS_RETRIES": str(preferences.live_status_retries),
    }
    config["StreamStatus"] = {
        "enabled": str(preferences.stream_status_enabled)
    }
    config["AccountInfo"] = {
        "refresh_interval": str(preferences.account_refresh_interval),
        "auto_refresh_enabled": str(preferences.account_auto_refresh_enabled),
    }
    config["CatalogCache"] = {
        "enabled": str(preferences.catalog_cache_enabled),
        "max_age_hours": str(preferences.catalog_cache_max_age_hours),
    }
    config["Logging"] = {
        "detailed": str(preferences.detailed_logging_enabled)
    }
    config["History"] = {
        "max_items_per_type": str(preferences.history_size)
    }
    config["TMDB"] = {
        "read_access_token": preferences.tmdb_read_access_token
    }
    write_config_file(filename, config)


def _bounded_int(config, section, option, fallback, minimum, maximum):
    """Read and clamp one integer without affecting neighbouring values."""
    try:
        value = config.getint(section, option, fallback=fallback)
    except (ValueError, configparser.Error):
        value = fallback
    return max(minimum, min(value, maximum))


def _boolean(config, section, option, fallback):
    """Read one boolean while tolerating manually edited invalid text."""
    try:
        return config.getboolean(section, option, fallback=fallback)
    except (ValueError, configparser.Error):
        return fallback
