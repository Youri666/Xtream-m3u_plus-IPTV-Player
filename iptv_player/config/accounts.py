"""Persistence helpers for IPTV account entries."""

import configparser
import uuid

from iptv_player.config.ini import write_config_file


ACCOUNT_SECTION_PREFIX = "Account:"


def load_accounts(file_path):
    """Return saved account names and serialized values in file order."""
    config = _read_config(file_path)
    accounts = {}
    for _account_id, section in _account_sections(config):
        name = section.get("name", "").strip()
        serialized_account = section.get("credentials", "")
        if name and serialized_account:
            accounts[name] = serialized_account

    # Keep direct API use compatible until the startup migration has run.
    if not accounts and "Credentials" in config:
        accounts = dict(config["Credentials"].items())
        startup_name = _legacy_startup_name(config)
        stored_name = _matching_account_name(accounts, startup_name)
        if stored_name and stored_name != startup_name:
            accounts = {
                startup_name if name == stored_name else name: value
                for name, value in accounts.items()
            }
    return accounts


def load_account(file_path, name):
    """Return one serialized account value, or ``None`` when it is absent."""
    accounts = load_accounts(file_path)
    stored_name = _matching_account_name(accounts, name)
    return accounts.get(stored_name) if stored_name else None


def load_startup_account(file_path):
    """Return the display name of the account selected for automatic startup."""
    config = _read_config(file_path)
    startup_id = config.get(
        "Startup credentials", "startup_account_id", fallback=""
    ).strip()
    if startup_id:
        section_name = _account_section_name(startup_id)
        if section_name in config:
            return config[section_name].get("name", "None")
        return "None"
    return _legacy_startup_name(config)


def save_startup_account(file_path, name):
    """Persist the selected startup account by stable internal identifier."""
    config = _read_config(file_path)
    if "Startup credentials" not in config:
        config["Startup credentials"] = {}

    account_id, _section = _find_account(config, name)
    config["Startup credentials"]["startup_account_id"] = account_id or ""
    config["Startup credentials"].pop("startup_credentials", None)
    write_config_file(file_path, config)


def save_account(file_path, method, name, credentials, old_name=None):
    """Create or replace an account while retaining its internal identifier."""
    validation_error = account_name_error(name)
    if validation_error:
        raise ValueError(validation_error)

    config = _read_config(file_path)
    account_id, section = _find_account(config, old_name or name)
    if account_id is None:
        account_id = uuid.uuid4().hex
        section_name = _account_section_name(account_id)
        config.add_section(section_name)
        section = config[section_name]

    startup_id = config.get(
        "Startup credentials", "startup_account_id", fallback=""
    ).strip()
    legacy_startup_name = _legacy_startup_name(config)

    section["name"] = name
    section["credentials"] = serialize_account(method, credentials)

    if "Startup credentials" not in config:
        config["Startup credentials"] = {}
    if startup_id == account_id or _same_account_name(legacy_startup_name, old_name):
        config["Startup credentials"]["startup_account_id"] = account_id
    config["Startup credentials"].pop("startup_credentials", None)
    write_config_file(file_path, config)


def delete_account(file_path, name):
    """Delete an account and clear it as the startup choice when necessary."""
    config = _read_config(file_path)
    account_id, _section = _find_account(config, name)
    if account_id is None:
        return False

    config.remove_section(_account_section_name(account_id))
    startup_id = config.get(
        "Startup credentials", "startup_account_id", fallback=""
    ).strip()
    if startup_id == account_id:
        config["Startup credentials"]["startup_account_id"] = ""
    write_config_file(file_path, config)
    return True


def serialize_account(method, credentials):
    """Serialize an account using the established credential representation."""
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


def account_name_error(name):
    """Return a user-facing validation error for an invalid account name."""
    name = str(name or "").strip()
    if not name:
        return "Please enter an account name."
    if name.casefold() == "none":
        return "The account name 'None' is reserved. Please choose another name."
    if any(character in name for character in "\r\n"):
        return "Account names cannot contain line breaks."
    return None


def _account_sections(config):
    """Yield stable account identifiers and their configuration sections."""
    for section_name in config.sections():
        if section_name.startswith(ACCOUNT_SECTION_PREFIX):
            yield section_name[len(ACCOUNT_SECTION_PREFIX):], config[section_name]


def _find_account(config, requested_name):
    """Return the identifier and section matching a display name without case."""
    for account_id, section in _account_sections(config):
        if _same_account_name(section.get("name", ""), requested_name):
            return account_id, section
    return None, None


def _account_section_name(account_id):
    return f"{ACCOUNT_SECTION_PREFIX}{account_id}"


def _legacy_startup_name(config):
    return config.get(
        "Startup credentials", "startup_credentials", fallback="None"
    )


def _matching_account_name(accounts, requested_name):
    requested_name = str(requested_name or "")
    for stored_name in accounts:
        if _same_account_name(stored_name, requested_name):
            return stored_name
    return None


def _same_account_name(first_name, second_name):
    return str(first_name or "").casefold() == str(second_name or "").casefold()


def _read_config(file_path):
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(file_path)
    return config
