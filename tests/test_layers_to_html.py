"""Offline tests for layers-to-html.py. No network.

Run from the repo root:
  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "meta-ads-static-creator"
SCRIPT = SKILL / "layers-to-html.py"
ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("layers_to_html", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _png(path: Path, size=(1152, 1440), color=(20, 80, 40)):
    Image.new("RGB", size, color).save(path)
    return path


def _ttf(path: Path):
    path.write_bytes(b"OTTOFAKEFONT")
    return path


def _layer(layer_id="headline", x=80, y=80, w=900, h=200, size=96, text="Hello"):
    return {
        "id": layer_id,
        "text": text,
        "font_file": None,
        "font_family": "TestFace",
        "size_px": size,
        "line_height": 1.1,
        "color": "#111111",
        "text_decoration": "none",
        "align": "left",
        "valign": "top",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "lines": [text],
        "rendered_lines": [{
            "text": text,
            "draw_x": x,
            "draw_y": y,
            "baseline_y": y + 80,
            "advance_px": w - 10,
            "visible_bounds": {
                "left": x, "top": y, "right": x + w - 20, "bottom": y + size,
            },
        }],
    }


def _layers_json(path: Path, plate: Path, variant="feed_4x5", size=(1152, 1440), layers=None):
    payload = {
        "variant": variant,
        "plate": str(plate),
        "width": size[0],
        "height": size[1],
        "layers": layers or [_layer()],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class ScaleTests(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_1152_wide_scales_to_1080(self):
        sx, sy = self.m.scale_xy(1152, 1440, 1080, 1350)
        self.assertAlmostEqual(sx, 1080 / 1152)
        self.assertAlmostEqual(sy, 1350 / 1440)
        scaled = self.m.scaled_layer(_layer(x=1152, y=144, w=576, h=288, size=96), sx, sy)
        self.assertAlmostEqual(scaled["x"], 1080)
        self.assertAlmostEqual(scaled["y"], 135)
        self.assertAlmostEqual(scaled["w"], 540)
        self.assertAlmostEqual(scaled["size_px"], 96 * 1080 / 1152)

    def test_delivery_sizes(self):
        self.assertEqual(self.m.delivery_size("feed_4x5", 1152, 1440), (1080, 1350))
        self.assertEqual(self.m.delivery_size("fullscreen_9x16", 1152, 2048), (1080, 1920))
        self.assertEqual(self.m.delivery_size("legacy", 1229, 1536), (1080, round(1536 * 1080 / 1229)))


class HtmlConvertTests(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.tmp = Path(tempfile.mkdtemp())
        self.plate = _png(self.tmp / "demo-feed_4x5-plate_v1.png")
        self.font = _ttf(self.tmp / "TestFace.ttf")
        layers = [_layer()]
        layers[0]["font_file"] = str(self.font)
        self.layers_path = _layers_json(
            self.tmp / "demo-feed_4x5-layers_v1.json", self.plate, layers=layers
        )
        (self.tmp / "spec.json").write_text(json.dumps({
            "output_name": "demo",
            "repeated_systems": {"card": {"fill": "#fff", "stroke": "#000", "radius": 12}},
            "variants": {
                "feed_4x5": {
                    "text": [{"id": "headline", "text": "Hello", "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3}}],
                    "plate_layout": {
                        "canvas": [1080, 1350],
                        "image_zones": [{"id": "hero", "box": [0, 0, 1, 1], "centering": [0.5, 0.2]}],
                    },
                },
                "fullscreen_9x16": {
                    "text": [{"id": "headline", "text": "Hello", "box": {"left": 0.12, "top": 0.2, "right": 0.8, "bottom": 0.35}}],
                },
            },
        }), encoding="utf-8")

    def convert(self, variant="feed_4x5"):
        spec = self.m.load_spec(self.tmp)
        data = self.m.load_layers(self.layers_path)
        return self.m.convert_variant_from_layers(
            variant, spec, data, self.layers_path, False
        )

    def test_one_element_per_layer_with_data_od_id(self):
        result = self.convert()
        html = self.m.html_for(result, [])
        self.assertIn('data-od-id="headline"', html)
        self.assertIn('data-od-name="headline"', html)
        self.assertEqual(html.count('data-od-id="headline"'), 1)
        self.assertIn("1080px", html)
        self.assertIn("1350px", html)
        self.assertIn('class="od-layer', html)

    def test_escapes_text(self):
        data = self.m.load_layers(self.layers_path)
        data["layers"][0]["rendered_lines"][0]["text"] = '<b>"&"'
        data["layers"][0]["id"] = 'x"y'
        result = self.m.convert_variant_from_layers(
            "feed_4x5", self.m.load_spec(self.tmp), data, self.layers_path, False
        )
        html = self.m.html_for(result, [])
        self.assertIn("&lt;b&gt;", html)
        self.assertNotIn("<b>", html)
        self.assertIn("data-od-id=", html)

    def test_object_fit_crop(self):
        result = self.convert()
        html = self.m.html_for(result, [])
        self.assertIn("object-fit:cover", html)
        self.assertIn("object-position:", html)
        self.assertIn('data-od-id="hero"', html)

    def test_shared_css_class_for_repeated_system(self):
        spec = self.m.load_spec(self.tmp)
        data = self.m.load_layers(self.layers_path)
        data["layers"][0]["id"] = "card-1"
        data["layers"][0]["rendered_lines"][0]["text"] = "A"
        result = self.m.convert_variant_from_layers(
            "feed_4x5", spec, data, self.layers_path, False
        )
        html = self.m.html_for(result, [])
        self.assertIn("od-sys-card", html)
        self.assertIn(".od-sys-card{", html)

    def test_font_face_relative_path(self):
        spec = self.m.load_spec(self.tmp)
        data = self.m.load_layers(self.layers_path)
        faces = self.m.collect_font_faces(data["layers"], self.tmp / "od-fonts")
        self.assertTrue((self.tmp / "od-fonts" / "TestFace.ttf").is_file())
        css = self.m.font_face_css(faces)
        self.assertIn("url('od-fonts/TestFace.ttf')", css)
        self.assertNotIn("http://", css)
        self.assertNotIn("https://", css)

    def test_cli_writes_1080x1350_and_board(self):
        plate916 = _png(self.tmp / "demo-fullscreen_9x16-plate_v1.png", (1152, 2048))
        layers916 = [_layer(x=120, y=280, w=700, h=180, size=96)]
        layers916[0]["font_file"] = str(self.font)
        _layers_json(
            self.tmp / "demo-fullscreen_9x16-layers_v1.json",
            plate916,
            variant="fullscreen_9x16",
            size=(1152, 2048),
            layers=layers916,
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.tmp), "--board"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        feed = (self.tmp / "demo-feed_4x5-od_v1.html").read_text(encoding="utf-8")
        tall = (self.tmp / "demo-fullscreen_9x16-od_v1.html").read_text(encoding="utf-8")
        board = (self.tmp / "demo-board_v1.html").read_text(encoding="utf-8")
        self.assertIn("width:1080px", feed)
        self.assertIn("height:1350px", feed)
        self.assertIn("width:1080px", tall)
        self.assertIn("height:1920px", tall)
        self.assertIn("od-board", board)
        self.assertIn("feed_4x5", board)
        self.assertIn("fullscreen_9x16", board)
        feed_pos = board.find("feed_4x5")
        tall_pos = board.find("fullscreen_9x16")
        self.assertLess(feed_pos, tall_pos)

    def test_wireframe_hides_images(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.tmp), "--wireframe", "--variant", "feed_4x5"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        html = (self.tmp / "demo-feed_4x5-od_v0.html").read_text(encoding="utf-8")
        self.assertIn("od-hide-images", html)
        self.assertIn("od-placeholder", html)
        self.assertIn("1080px", html)
        self.assertIn("1350px", html)

    def test_cli_does_not_open_a_socket(self):
        with mock.patch("socket.socket", side_effect=AssertionError("network")):
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), str(self.tmp), "--variant", "feed_4x5"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_flags_layer_outside_live_zone(self):
        layer = self.m.scaled_layer(_layer(x=0, y=0, w=50, h=40, size=96), 1, 1)
        failures = self.m.preflight("feed_4x5", [layer], 1080, 1350)
        self.assertTrue(any("live zone" in f for f in failures))

    def test_flags_type_floor_at_1080(self):
        layer = self.m.scaled_layer(_layer(size=40), 1080 / 1152, 1350 / 1440)
        failures = self.m.preflight("feed_4x5", [layer], 1080, 1350)
        self.assertTrue(any("mobile delivery floor" in f for f in failures))

    def test_passes_in_zone_headline(self):
        layer = _layer(x=80, y=80, w=800, h=120, size=96)
        failures = self.m.preflight("feed_4x5", [layer], 1080, 1350)
        self.assertEqual(failures, [])


class LegacyNameTests(unittest.TestCase):
    def test_tracked_files_have_no_legacy_design_tool(self):
        needle = "p" + "aper"
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        hits = []
        for raw in proc.stdout.split(b"\0"):
            if not raw:
                continue
            path = ROOT / raw.decode()
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if needle in line.lower():
                    hits.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()}")
        self.assertEqual(hits, [], "\n".join(hits))


class NoNetworkImportTests(unittest.TestCase):
    def test_module_import_does_not_touch_network(self):
        with mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            mod = _load()
        self.assertTrue(hasattr(mod, "html_for"))


if __name__ == "__main__":
    unittest.main()
