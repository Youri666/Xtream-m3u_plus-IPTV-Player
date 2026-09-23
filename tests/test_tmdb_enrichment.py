import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


def enrichment_methods():
    """Extract enrichment methods without constructing the full Qt application."""
    source = Path(__file__).resolve().parents[1] / "IPTVPlayer.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    app_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "IPTVPlayerApp"
    )
    names = {"_metadata_is_missing", "_apply_tmdb_enrichment"}
    module = ast.Module(
        body=[
            node for node in app_class.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ],
        type_ignores=[],
    )
    namespace = {}
    exec(compile(module, str(source), "exec"), namespace)
    return {name: namespace[name] for name in names}


class TmdbEnrichmentTests(unittest.TestCase):
    def test_only_missing_provider_fields_are_replaced(self):
        harness = type("EnrichmentHarness", (), enrichment_methods())()
        info_box = Mock()
        info_box.tmdb_code = "42"
        harness.info_boxes = {"Movies": info_box}
        harness._is_current_info_request = Mock(return_value=True)
        harness.fetch_image = Mock()
        provider_info = {
            "name": "Provider title",
            "genre": "",
            "duration": None,
            "movie_image": "provider-cover",
            "youtube_trailer": "",
        }

        harness._apply_tmdb_enrichment(
            "movie",
            "42",
            {
                "name": "TMDB title",
                "genre": "Drama",
                "duration": 95,
                "poster_url": "https://image/poster.jpg",
                "youtube_trailer": "trailer-key",
            },
            provider_info,
            7,
        )

        info_box.name.setText.assert_not_called()
        info_box.genre.setText.assert_called_once_with("Genre: Drama")
        info_box.duration.setText.assert_called_once_with("Duration: 95 min")
        harness.fetch_image.assert_not_called()
        self.assertEqual(info_box.yt_code, "trailer-key")
        info_box.set_trailer_available.assert_called_once_with(True)

    def test_stale_tmdb_response_is_ignored(self):
        harness = type("EnrichmentHarness", (), enrichment_methods())()
        info_box = Mock()
        info_box.tmdb_code = "42"
        harness.info_boxes = {"Movies": info_box}
        harness._is_current_info_request = Mock(return_value=False)
        harness.fetch_image = Mock()

        harness._apply_tmdb_enrichment(
            "movie", "42", {"genre": "Drama"}, {"genre": ""}, 2
        )

        info_box.genre.setText.assert_not_called()


if __name__ == "__main__":
    unittest.main()
