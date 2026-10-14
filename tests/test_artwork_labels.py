"""Verify smooth source scaling and physical resolution at common DPI factors."""
import os
import unittest
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication
from iptv_player.ui.image_labels import ArtworkLabel


class DensityLabel(ArtworkLabel):
    density = 1.0

    def devicePixelRatioF(self):
        return self.density


class ArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.images = Path(__file__).resolve().parents[1] / "images"

    def test_icon_is_smooth_at_standard_and_high_dpi(self):
        source = QPixmap(str(self.images / "yt_icon_rgb.png"))
        for density in (1, 1.5, 2, 3):
            with self.subTest(density=density):
                label = DensityLabel()
                label.density = density
                label.set_artwork(source, height=30)
                pixmap = label.pixmap()
                self.assertEqual(pixmap.height(), round(30 * density))
                self.assertEqual(pixmap.devicePixelRatioF(), density)
                expected = source.scaled(pixmap.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.assertEqual(pixmap.toImage().pixelColor(10, 10), expected.toImage().pixelColor(10, 10))

    def test_monitor_change_renders_again_from_original_pixels(self):
        label = DensityLabel()
        source = QPixmap(str(self.images / "yt_icon_rgb.png"))
        label.set_artwork(source, height=30)
        label.density = 3
        label._render_artwork()
        self.assertEqual(label.pixmap().height(), 90)
        expected = source.scaled(label.pixmap().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        actual = label.pixmap().toImage()
        actual.setDevicePixelRatio(1)
        self.assertEqual(actual, expected.toImage())

    def test_live_logo_preserves_previous_width_and_aspect_ratio(self):
        source = QPixmap(600, 300)
        source.fill(Qt.red)
        label = DensityLabel()
        label.set_artwork(source, width=200)
        self.assertEqual(label.pixmap().size(), QSize(200, 100))

    def test_tmdb_vector_renders_at_target_resolution(self):
        label = DensityLabel()
        label.density = 3
        label.set_artwork_file(str(self.images / "primary_full-TMDB.svg"), height=30)
        self.assertFalse(label.pixmap().isNull())
        self.assertEqual(label.pixmap().height(), 90)

    def test_status_circle_keeps_color_size_and_transparent_smooth_edge(self):
        import ast
        from types import SimpleNamespace
        tree = ast.parse((self.images.parent / "IPTVPlayer.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "IPTVPlayerApp")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "status_pixmap")
        module = ast.Module(body=[method], type_ignores=[])
        namespace = dict(QPixmap=QPixmap, Qt=Qt)
        exec(compile(ast.fix_missing_locations(module), "status_circle", "exec"), namespace)
        for name in ("online", "offline", "maybe", "unknown"):
            with self.subTest(status=name):
                filename = str(self.images / (name + "_status.png"))
                pixmap = namespace["status_pixmap"](SimpleNamespace(devicePixelRatioF=lambda: 1), filename, 24)
                self.assertAlmostEqual(pixmap.width() / pixmap.devicePixelRatioF(), 24, places=3)
                image = pixmap.toImage()
                source = QPixmap(filename).toImage()
                self.assertEqual(image.pixelColor(image.width() // 2, image.height() // 2),
                                 source.pixelColor(source.width() // 2, source.height() // 2))
                self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
                self.assertTrue(any(0 < image.pixelColor(x, y).alpha() < 255
                                    for x in range(image.width()) for y in range(image.height())))
                label = DensityLabel()
                label.density = 3
                label.setPixmap(pixmap)
                self.assertEqual(label.pixmap().width(), 72)
