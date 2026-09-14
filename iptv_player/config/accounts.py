"""Persistence helpers for IPTV account entries."""

import configparser

from iptv_player.config.ini import write_config_file


def load_accounts(file_path):
    """Return saved account names and serialized values in file order."""
    config = _read_config(file_path)
    if "Credentials" not in config:
        return {}
    return dict(config["Credentials"].items())


def load_account(file_path, name):
    """Return one serialized account value, or ``None`` when it is absent."""
    return load_accounts(file_path).get(name)


def load_startup_account(file_path):
    """Return the account selected for automatic startup."""
    config = _read_config(file_path)
    return config.get("Startup credentials", "startup_credentials", fallback="None")


def save_startup_account(file_path, name):
    """Persist the account selected for automatic startup."""
    config = _read_config(file_path)
    if "Startup credentials" not in config:
        config["Startup credentials"] = {}
    config["Startup credentials"]["startup_credentials"] = name
    write_config_file(file_path, config)


def save_account(file_path, method, name, credentials, old_name=None):
    """Create or replace an account and preserve startup selection on rename."""
    config = _read_config(file_path)
    if "Credentials" not in config:
        config["Credentials"] = {}

    if old_name and old_name != name:
        config["Credentials"].pop(old_name, None)
        if load_startup_account_from_config(config) == old_name:
            if "Startup credentials" not in config:
                config["Startup credentials"] = {}
            config["Startup credentials"]["startup_credentials"] = name

    config["Credentials"][name] = serialize_account(method, credentials)
    write_config_file(file_path, config)


def delete_account(file_path, name):
    """Delete an account and clear it as the startup choice when necessary."""
    config = _read_config(file_path)
    if "Credentials" not in config or name not in config["Credentials"]:
        return False

    del config["Credentials"][name]
    if load_startup_account_from_config(config) == name:
        if "Startup credentials" not in config:
            config["Startup credentials"] = {}
        config["Startup credentials"]["startup_credentials"] = "None"
    write_config_file(file_path, config)
    return True


def serialize_account(method, credentials):
    """Serialize an account using the established INI representation."""
    if method not in ("manual", "m3u_plus"):
        raise ValueError(f"Unsupported account method: {method}")
    return "|".join((method, *credentials))


def parse_account(serialized_account):
    """Return a validated account method and fields from persisted text."""
    parts = str(serialized_account or "").split("|")
    expected_field_counts = {"manual": 6, "m3u_plus": 4}
    if not parts or parts[0] not in expected_field_counts:
        return None

    method = parts[0]
    field_count = expected_field_counts[method]
    if len(parts) < field_count + 1:
        return None
    return method, parts[1:field_count + 1]


def load_startup_account_from_config(config):
    return config.get("Startup credentials", "startup_credentials", fallback="None")


def _read_config(file_path):
    config = configparser.ConfigParser()
    # Account names are user-facing labels and must retain their original case.
    config.optionxform = str
    config.read(file_path)
    return config
