"""Shared application palette and native window theme support."""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette


def is_system_dark(app):
    """Return whether the operating-system application theme is dark."""
    if sys.platform.startswith("win"):
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return value == 0
        except OSError:
            return False

    try:
        return application_palette_is_dark(app)
    except Exception:
        return False


def apply_application_theme(app, theme_name):
    """Apply one shared palette to the main application and isolated player."""
    selected_theme = theme_name if theme_name in ("System", "Light", "Dark") else "System"
    dark = selected_theme == "Dark" or (
        selected_theme == "System" and is_system_dark(app)
    )
    if dark:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(45, 45, 48))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.AlternateBase, QColor(45, 45, 48))
        palette.setColor(QPalette.ToolTipBase, QColor(45, 45, 48))
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(45, 45, 48))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(91, 141, 239))
        palette.setColor(QPalette.Highlight, QColor(91, 141, 239))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
        palette.setColor(
            QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127)
        )
        app.setPalette(palette)
    else:
        app.setPalette(app.style().standardPalette())
    return dark


def apply_windows_title_bar_theme(widget, dark):
    """Synchronize a native Windows title bar with the Qt application theme."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        enabled = ctypes.c_int(1 if dark else 0)
        hwnd = int(widget.winId())
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )
            if result == 0:
                break

        caption = widget.palette().color(QPalette.Window)
        caption_color = ctypes.c_uint(
            caption.red() | (caption.green() << 8) | (caption.blue() << 16)
        )
        text = widget.palette().color(QPalette.WindowText)
        text_color = ctypes.c_uint(
            text.red() | (text.green() << 8) | (text.blue() << 16)
        )
        for attribute, color in ((35, caption_color), (36, text_color)):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(color), ctypes.sizeof(color)
            )
    except Exception:
        pass


def application_palette_is_dark(app):
    """Return whether the palette currently applied to Qt is dark."""
    background = app.palette().color(QPalette.Window)
    luminance = (
        0.299 * background.red()
        + 0.587 * background.green()
        + 0.114 * background.blue()
    )
    return luminance < 128

