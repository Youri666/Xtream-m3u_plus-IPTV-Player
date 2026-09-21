"""Application-wide logging and Qt startup configuration."""

import atexit
import faulthandler
import logging
import os
from os import path
import sys
import threading
import traceback

from PyQt5 import QtCore
from PyQt5.QtGui import QFont

from iptv_player.config import load_advanced_preferences, writable_data_directory
from iptv_player.utils.privacy import redact_log_credentials


class _CredentialRedactionFilter(logging.Filter):
    """Remove provider credentials from every record before it reaches log.txt."""

    def filter(self, record):
        record.msg = redact_log_credentials(record.getMessage())
        record.args = ()
        return True


class _StreamToLogger:
    """Mirror a text stream to the application log one complete line at a time."""

    def __init__(self, original, level):
        self.original = original
        self.level = level
        self._buffer = ""

    def write(self, data):
        try:
            if self.original is not None:
                self.original.write(data)
        except Exception:
            pass

        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                logging.log(self.level, line)

    def flush(self):
        try:
            if self.original is not None:
                self.original.flush()
        except Exception:
            pass

    def isatty(self):
        return False


_FAULT_LOG_STREAMS = []


def install_logging(append=False, process_name="Main application"):
    """Capture Python diagnostics in ``log.txt`` for one application process."""
    if sys.platform.startswith("darwin"):
        application_dir = writable_data_directory()
    elif getattr(sys, "frozen", False):
        application_dir = path.dirname(path.abspath(sys.executable))
    else:
        application_dir = path.dirname(path.dirname(path.abspath(__file__)))

    os.makedirs(application_dir, exist_ok=True)
    log_path = path.join(application_dir, "log.txt")
    user_data_file = path.join(application_dir, "userdata.ini")
    log_level = (
        logging.DEBUG
        if load_advanced_preferences(user_data_file).detailed_logging_enabled
        else logging.INFO
    )

    # Truncate once in the main process, then let both application processes use
    # append mode so their file positions cannot overwrite each other's records.
    if not append:
        with open(log_path, "w", encoding="utf-8"):
            pass

    try:
        logging.basicConfig(
            filename=log_path,
            filemode="a",
            level=log_level,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
            force=True,
        )
    except TypeError:
        # Python versions before 3.9 do not support the encoding argument.
        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(log_level)

    # Third-party DEBUG records may include complete request URLs. Attach the
    # filter to every output handler so those credentials never reach the file.
    for handler in logging.getLogger().handlers:
        handler.addFilter(_CredentialRedactionFilter())

    sys.stdout = _StreamToLogger(sys.stdout, logging.INFO)
    sys.stderr = _StreamToLogger(sys.stderr, logging.ERROR)

    def handle_unhandled_exception(exc_type, exc, tb):
        formatted = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.error("Unhandled exception:\n%s", formatted)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = handle_unhandled_exception

    def handle_thread_exception(args):
        handle_unhandled_exception(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = handle_thread_exception

    # faulthandler writes tracebacks for fatal Python signals that bypass normal
    # exception handling. Keep its file object alive for the complete process.
    try:
        fault_stream = open(log_path, "a", encoding="utf-8")
        faulthandler.enable(file=fault_stream, all_threads=True)
        _FAULT_LOG_STREAMS.append(fault_stream)
    except (OSError, RuntimeError):
        logging.exception("Could not enable fatal Python traceback logging")

    logging.info(
        "=== %s session start (log lives at %s) ===", process_name, log_path
    )
    atexit.register(
        lambda: logging.info("=== %s session end ===", process_name)
    )


def set_detailed_logging(enabled):
    """Change diagnostic verbosity immediately without restarting the application."""
    logging.getLogger().setLevel(logging.DEBUG if enabled else logging.INFO)


def configure_qt_application(app):
    """Apply the same visual defaults in the main and player processes."""
    from iptv_player.ui.theme import remember_system_palette

    _install_qt_message_logging()
    remember_system_palette(app)
    app.setStyle("Fusion")

    # Use fonts with broad Unicode coverage so provider titles remain readable.
    if sys.platform.startswith("win"):
        app.setFont(QFont("Segoe UI", 10))
    elif sys.platform.startswith("darwin"):
        app.setFont(QFont("Helvetica Neue", 13))
    else:
        app.setFont(QFont("Noto Sans", 10))


def _install_qt_message_logging():
    """Route Qt diagnostics through the same filtered application logger."""
    levels = {
        QtCore.QtDebugMsg: logging.DEBUG,
        QtCore.QtWarningMsg: logging.WARNING,
        QtCore.QtCriticalMsg: logging.ERROR,
        QtCore.QtFatalMsg: logging.CRITICAL,
    }
    # QtInfoMsg is absent from some older Qt 5 bindings still used by Linux
    # distributions, so register it only when the binding exposes it.
    qt_info_message = getattr(QtCore, "QtInfoMsg", None)
    if qt_info_message is not None:
        levels[qt_info_message] = logging.INFO

    def handle_qt_message(message_type, context, message):
        location = ""
        if context is not None and context.file:
            location = f" ({context.file}:{context.line})"
        logging.log(
            levels.get(message_type, logging.INFO),
            "Qt: %s%s",
            message,
            location,
        )

    QtCore.qInstallMessageHandler(handle_qt_message)
