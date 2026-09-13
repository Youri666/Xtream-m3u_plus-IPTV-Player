"""Runtime network settings shared by provider workers and dialogs."""

from dataclasses import dataclass


DEFAULT_CONNECTION_TIMEOUT = 3
DEFAULT_READ_TIMEOUT = 30
DEFAULT_LIVE_STATUS_TIMEOUT = 7
DEFAULT_LIVE_STATUS_RETRIES = 2
DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL = 60
DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS = 24

# Retries are additional attempts, so the default allows three probes in total.
LIVE_STATUS_RETRY_DELAY = 0.5
LIVE_STATUS_CHUNK_SIZE = 4096
MAX_LIVE_STATUS_RETRIES = 10


@dataclass
class NetworkSettings:
    """Hold network values that can be changed while the application runs."""

    connection_timeout: int = DEFAULT_CONNECTION_TIMEOUT
    read_timeout: int = DEFAULT_READ_TIMEOUT
    live_status_timeout: int = DEFAULT_LIVE_STATUS_TIMEOUT
    live_status_retries: int = DEFAULT_LIVE_STATUS_RETRIES


NETWORK_SETTINGS = NetworkSettings()
