"""Regression coverage for accepting an update during application startup."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def main_function(namespace):
    """Extract main() without importing or starting the complete Qt application."""
    source = Path(__file__).resolve().parents[1] / "IPTVPlayer.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    main_node = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    module = ast.Module(body=[main_node], type_ignores=[])
    exec(compile(module, str(source), "exec"), namespace)
    return namespace["main"]


class UpdateShutdownTests(unittest.TestCase):
    def test_accepted_startup_update_does_not_show_main_window(self):
        player = Mock()
        player._update_exit_requested = True
        app = Mock()
        application_factory = Mock(return_value=app)
        namespace = {
            "sys": SimpleNamespace(argv=[], exit=Mock()),
            "run_embedded_player_process": Mock(),
            "configure_qt_high_dpi": Mock(),
            "install_logging": Mock(),
            "QApplication": application_factory,
            "configure_qt_application": Mock(),
            "IPTVPlayerApp": Mock(return_value=player),
            "QtWidgets": SimpleNamespace(qApp=Mock()),
        }

        main_function(namespace)()

        player.show.assert_not_called()
        app.exec_.assert_not_called()


if __name__ == "__main__":
    unittest.main()
