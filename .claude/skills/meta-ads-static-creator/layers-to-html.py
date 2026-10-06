#!/usr/bin/env python3
"""
layers-to-html.py — convert layers.json (plate pixels) to Open Design HTML.

Usage (from project root):
  python3 .claude/skills/meta-ads-static-creator/layers-to-html.py \\
    brands/[brand]/generation/meta-ads-static-creator/[output-name] \\
    --variant feed_4x5

  python3 .claude/skills/meta-ads-static-creator/layers-to-html.py OUT --wireframe --variant feed_4x5
  python3 .claude/skills/meta-ads-static-creator/layers-to-html.py OUT --board
  python3 .claude/skills/meta-ads-static-creator/layers-to-html.py OUT --preflight --variant feed_4x5

Writes [name]-[variant]-od_vN.html (1080×1350 or 1080×1920), copies brand fonts
into od-fonts/, and with --board writes [name]-board_vN.html (both frames
side by side). --wireframe emits placeholder image boxes and adds
od-hide-images. --preflight checks scaled bounds and type floors; it writes
nothing.

Free — no network.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from html import escape
from pathlib import Path

DELIVERY = {
    "feed_4x5": (1080, 1350),
    "fullscreen_9x16": (1080, 1920),
}

LIVE_ZONES = {
    "feed_4x5": (54, 54, 1026, 1296),
    "fullscreen_9x16": (90, 250, 990, 1570),
}

RAIL_9X16 = (840, 560, 1080, 1500)

MOBILE_FLOORS = {
    "legal": 20,
    "footnote": 20,
    "caption": 30,
    "subline": 30,
    "stat": 96,
    "headline": 88,
    "price": 34,
    "cta": 34,
    "kicker": 28,
    "eyebrow": 28,
    "before": 28,
    "after": 28,
    "order": 28,
    "save": 28,
    "code": 28,
    "old-price": 24,
}

FONT_FORMAT = {
    ".ttf": "truetype",
    ".otf": "opentype",
    ".woff": "woff",
    ".woff2": "woff2",
}


def _arg(flag, default=None):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith("--"):
        sys.exit(f"Error: {flag} requires a value.")
    return sys.argv[i + 1]


def _latest(out: Path, pattern: str):
    found = sorted(
        out.glob(pattern),
        key=lambda p: int(p.stem.rsplit("_v", 1)[1]),
    )
    return found[-1] if found else None


def _version_of(path: Path) -> str:
    return path.stem.rsplit("_v", 1)[1]


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-")
    return slug or "layer"


def delivery_size(variant: str | None, src_w: int, src_h: int) -> tuple[int, int]:
    if variant in DELIVERY:
        return DELIVERY[variant]
    if not src_w:
        sys.exit("Error: layers.json width must be greater than 0.")
    return 1080, round(src_h * 1080 / src_w)


def scale_xy(src_w: int, src_h: int, dest_w: int, dest_h: int) -> tuple[float, float]:
    if src_w <= 0 or src_h <= 0:
        sys.exit("Error: layers.json width and height must be greater than 0.")
    return dest_w / src_w, dest_h / src_h


def mobile_floor(layer_id: str, variant: str | None) -> int | None:
    if variant not in DELIVERY:
        return None
    name = layer_id.lower()
    for key, floor in MOBILE_FLOORS.items():
        if key in name:
            return floor
    return None


def system_class_for(layer_id: str, repeated_systems: dict) -> str:
    lid = layer_id.lower()
    for name in repeated_systems:
        key = str(name).lower()
        if lid == key or lid.startswith(key + "-") or lid.startswith(key + "_"):
            return f"od-sys-{_slug(name)}"
    return ""


def repeated_system_css(repeated_systems: dict) -> str:
    chunks = []
    for name, spec in repeated_systems.items():
        if not isinstance(spec, dict):
            spec = {}
        cls = f".od-sys-{_slug(name)}"
        decls = ["box-sizing:border-box"]
        if spec.get("fill"):
            decls.append(f"background:{spec['fill']}")
        if spec.get("stroke"):
            width = spec.get("stroke_width", spec.get("rule_width", 1))
            decls.append(f"border:{width}px solid {spec['stroke']}")
        if spec.get("radius") is not None:
            decls.append(f"border-radius:{spec['radius']}px")
        if spec.get("padding") is not None:
            decls.append(f"padding:{spec['padding']}px")
        chunks.append(f"{cls}{{{';'.join(decls)}}}")
    return "".join(chunks)


def object_position(centering) -> str:
    if not centering or len(centering) < 2:
        return "50% 50%"
    cx, cy = float(centering[0]), float(centering[1])
    return f"{cx * 100:.4g}% {cy * 100:.4g}%"


def collect_font_faces(layers: list, dest_dir: Path) -> list[tuple[str, str, str]]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    seen = set()
    faces = []
    for layer in layers:
        src = layer.get("font_file")
        family = layer.get("font_family") or "sans-serif"
        if not src:
            continue
        path = Path(src)
        if not path.is_file():
            continue
        key = (family, path.name)
        if key in seen:
            continue
        seen.add(key)
        shutil.copy2(path, dest_dir / path.name)
        fmt = FONT_FORMAT.get(path.suffix.lower(), "truetype")
        faces.append((family, path.name, fmt))
    return faces


def font_face_css(faces: list[tuple[str, str, str]], fonts_rel: str = "od-fonts") -> str:
    chunks = []
    for family, filename, fmt in faces:
        chunks.append(
            "@font-face{"
            f"font-family:{_css_str(family)};"
            f"src:url('{fonts_rel}/{filename}') format('{fmt}');"
            "}"
        )
    return "".join(chunks)


def _css_str(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _style(decls: dict) -> str:
    parts = []
    for key, val in decls.items():
        if val is None or val == "":
            continue
        parts.append(f"{key}:{val}")
    return ";".join(parts)


def scaled_layer(layer: dict, sx: float, sy: float) -> dict:
    out = dict(layer)
    out["x"] = layer["x"] * sx
    out["y"] = layer["y"] * sy
    out["w"] = layer["w"] * sx
    out["h"] = layer["h"] * sy
    out["size_px"] = layer.get("size_px", 0) * sx
    out["font_ascent_px"] = layer.get("font_ascent_px", 0) * sy
    out["font_descent_px"] = layer.get("font_descent_px", 0) * sy
    rendered = []
    for line in layer.get("rendered_lines") or []:
        item = dict(line)
        item["draw_x"] = line["draw_x"] * sx
        item["draw_y"] = line["draw_y"] * sy
        item["baseline_y"] = line.get("baseline_y", line["draw_y"]) * sy
        item["advance_px"] = line.get("advance_px", 0) * sx
        bounds = line.get("visible_bounds") or {}
        item["visible_bounds"] = {
            "left": bounds.get("left", 0) * sx,
            "top": bounds.get("top", 0) * sy,
            "right": bounds.get("right", 0) * sx,
            "bottom": bounds.get("bottom", 0) * sy,
        }
        rendered.append(item)
    out["rendered_lines"] = rendered
    return out


def layers_from_spec(variant_spec: dict, dest_w: int, dest_h: int) -> list[dict]:
    layers = []
    for box in variant_spec.get("text", []):
        b = box["box"]
        x0, y0 = b["left"] * dest_w, b["top"] * dest_h
        x1, y1 = b["right"] * dest_w, b["bottom"] * dest_h
        size = box.get("size", 0.03) * dest_h
        text = box.get("text", "")
        if box.get("uppercase"):
            text = text.upper()
        layers.append({
            "id": box["id"],
            "text": text,
            "font_file": None,
            "font_family": box.get("font", "body"),
            "size_px": size,
            "line_height": box.get("line_height", 1.15),
            "color": box.get("color", "#000000"),
            "text_decoration": box.get("text_decoration", "none"),
            "align": box.get("align", "left"),
            "valign": box.get("valign", "top"),
            "x": x0,
            "y": y0,
            "w": x1 - x0,
            "h": y1 - y0,
            "lines": text.split("\n"),
            "rendered_lines": [],
        })
    return layers


def image_zones_from_spec(variant_spec: dict, dest_w: int, dest_h: int) -> list[dict]:
    layout = variant_spec.get("plate_layout") or {}
    zones = []
    for i, zone in enumerate(layout.get("image_zones", [])):
        box = zone["box"]
        x0, y0 = box[0] * dest_w, box[1] * dest_h
        x1, y1 = box[2] * dest_w, box[3] * dest_h
        zones.append({
            "id": zone.get("id", f"image-zone-{i + 1}"),
            "x": x0,
            "y": y0,
            "w": x1 - x0,
            "h": y1 - y0,
            "object_position": object_position(zone.get("centering")),
            "object_fit": zone.get("object_fit", "cover"),
        })
    return zones


def layer_markup(layer: dict, id_prefix: str = "") -> str:
    lid = _slug(layer["id"])
    html_id = _slug(f"{id_prefix}-{lid}" if id_prefix else lid)
    name = escape(str(layer["id"]), quote=True)
    classes = ["od-layer"]
    extra = layer.get("system_class")
    if extra:
        classes.append(extra)
    align = layer.get("align", "left")
    decoration = layer.get("text_decoration") or "none"
    family = layer.get("font_family") or "sans-serif"
    style = _style({
        "left": f"{layer['x']:.2f}px",
        "top": f"{layer['y']:.2f}px",
        "width": f"{layer['w']:.2f}px",
        "height": f"{layer['h']:.2f}px",
        "font-family": _css_str(family),
        "font-size": f"{layer['size_px']:.2f}px",
        "line-height": str(layer.get("line_height", 1.15)),
        "color": layer.get("color", "#000000"),
        "text-align": align,
        "text-decoration": decoration if decoration != "none" else None,
    })
    lines = layer.get("rendered_lines") or []
    if lines:
        inner = []
        for i, line in enumerate(lines):
            lx = line["draw_x"] - layer["x"]
            ly = line["draw_y"] - layer["y"]
            inner.append(
                f'<span class="od-line" data-od-line="{i}" '
                f'style="left:{lx:.2f}px;top:{ly:.2f}px">'
                f'{escape(line.get("text", ""))}</span>'
            )
        body = "".join(inner)
    else:
        body = "<br>".join(escape(t) for t in (layer.get("lines") or [layer.get("text") or ""]))
    return (
        f'<div class="{" ".join(classes)}" id="od-{html_id}" '
        f'data-od-id="{name}" data-od-name="{name}" style="{style}">{body}</div>'
    )


def placeholder_markup(zone: dict, id_prefix: str = "") -> str:
    lid = _slug(zone["id"])
    html_id = _slug(f"{id_prefix}-{lid}" if id_prefix else lid)
    name = escape(str(zone["id"]), quote=True)
    style = _style({
        "left": f"{zone['x']:.2f}px",
        "top": f"{zone['y']:.2f}px",
        "width": f"{zone['w']:.2f}px",
        "height": f"{zone['h']:.2f}px",
    })
    return (
        f'<div class="od-placeholder" id="od-{html_id}-ph" '
        f'data-od-id="{name}-placeholder" data-od-name="{name} placeholder" '
        f'style="{style}"></div>'
    )


def plate_markup(src: str, dest_w: int, dest_h: int, position: str = "50% 50%",
                 fit: str = "cover", id_prefix: str = "") -> str:
    if not src:
        return ""
    html_id = _slug(f"{id_prefix}-plate" if id_prefix else "plate")
    style = _style({
        "width": f"{dest_w}px",
        "height": f"{dest_h}px",
        "object-fit": fit,
        "object-position": position,
    })
    return (
        f'<img class="od-image" id="od-{html_id}" data-od-id="plate" data-od-name="plate" '
        f'alt="" src="{escape(src, quote=True)}" style="{style}">'
    )


def stage_css(dest_w: int, dest_h: int, extra: str = "") -> str:
    return (
        "html,body{margin:0;padding:0;background:#111}"
        ".od-stage{position:relative;overflow:hidden;background:#000;"
        f"width:{dest_w}px;height:{dest_h}px}}"
        ".od-image{position:absolute;left:0;top:0;display:block}"
        ".od-layer{position:absolute;box-sizing:border-box;white-space:pre-wrap}"
        ".od-line{position:absolute;left:0;top:0;white-space:pre}"
        ".od-placeholder{display:none;position:absolute;box-sizing:border-box;"
        "background:#d0d0d0;outline:2px dashed #666}"
        ".od-hide-images .od-image{visibility:hidden}"
        ".od-hide-images .od-placeholder{display:block}"
        ".od-board{display:flex;gap:48px;padding:48px;align-items:flex-start}"
        + extra
    )


def wrap_html(title: str, css: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>{escape(title)}</title>\n"
        f"<style>{css}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def render_stage(
    variant: str,
    dest_w: int,
    dest_h: int,
    layers: list[dict],
    plate_src: str,
    image_zones: list[dict],
    hide_images: bool,
    repeated_systems: dict,
    centering=None,
    id_prefix: str = "",
) -> str:
    classes = ["od-stage"]
    if hide_images:
        classes.append("od-hide-images")
    stage_id = _slug(id_prefix or variant)
    parts = [
        f'<div class="{" ".join(classes)}" id="od-stage-{stage_id}" '
        f'data-od-id="{escape(variant, quote=True)}" '
        f'data-od-name="{escape(variant, quote=True)}" '
        f'style="width:{dest_w}px;height:{dest_h}px">'
    ]
    if not image_zones:
        parts.append(plate_markup(plate_src, dest_w, dest_h, object_position(centering),
                                 id_prefix=id_prefix))
        parts.append(placeholder_markup({
            "id": "image-zone", "x": 0, "y": 0, "w": dest_w, "h": dest_h,
        }, id_prefix=id_prefix))
    else:
        for zone in image_zones:
            zid = _slug(f"{id_prefix}-{zone['id']}" if id_prefix else zone["id"])
            zname = escape(str(zone["id"]), quote=True)
            style = _style({
                "left": f"{zone['x']:.2f}px",
                "top": f"{zone['y']:.2f}px",
                "width": f"{zone['w']:.2f}px",
                "height": f"{zone['h']:.2f}px",
                "object-fit": zone.get("object_fit", "cover"),
                "object-position": zone.get("object_position", "50% 50%"),
                "position": "absolute",
            })
            src = zone.get("src") or plate_src
            if src:
                parts.append(
                    f'<img class="od-image" id="od-{zid}" data-od-id="{zname}" '
                    f'data-od-name="{zname}" alt="" src="{escape(src, quote=True)}" '
                    f'style="{style}">'
                )
            parts.append(placeholder_markup(zone, id_prefix=id_prefix))
    for layer in layers:
        layer = dict(layer)
        layer["system_class"] = system_class_for(str(layer["id"]), repeated_systems)
        parts.append(layer_markup(layer, id_prefix=id_prefix))
    parts.append("</div>")
    return "".join(parts)


def aabb_overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def layer_bounds(layer: dict) -> tuple[float, float, float, float]:
    rendered = layer.get("rendered_lines") or []
    if rendered:
        lefts, tops, rights, bottoms = [], [], [], []
        for line in rendered:
            b = line.get("visible_bounds") or {}
            lefts.append(b.get("left", layer["x"]))
            tops.append(b.get("top", layer["y"]))
            rights.append(b.get("right", layer["x"] + layer["w"]))
            bottoms.append(b.get("bottom", layer["y"] + layer["h"]))
        return min(lefts), min(tops), max(rights), max(bottoms)
    return layer["x"], layer["y"], layer["x"] + layer["w"], layer["y"] + layer["h"]


def preflight(variant: str, layers: list[dict], dest_w: int, dest_h: int,
              check_floors: bool = True) -> list[str]:
    failures = []
    live = LIVE_ZONES.get(variant)
    if live:
        lx0, ly0, lx1, ly1 = live
        for layer in layers:
            b = layer_bounds(layer)
            if b[0] < lx0 or b[1] < ly0 or b[2] > lx1 or b[3] > ly1:
                failures.append(
                    f"{layer['id']}: bounds {tuple(round(v, 1) for v in b)} "
                    f"leave the {variant} live zone {live}"
                )
    if variant == "fullscreen_9x16":
        rx0, ry0, rx1, ry1 = RAIL_9X16
        for layer in layers:
            b = layer_bounds(layer)
            if aabb_overlap(b, RAIL_9X16):
                failures.append(
                    f"{layer['id']}: overlaps the 9:16 platform rail "
                    f"({rx0}–{rx1}, {ry0}–{ry1})"
                )
    for i, a in enumerate(layers):
        ba = layer_bounds(a)
        for b in layers[i + 1:]:
            bb = layer_bounds(b)
            if aabb_overlap(ba, bb):
                failures.append(f"{a['id']} overlaps {b['id']}")
    if check_floors:
        for layer in layers:
            floor = layer.get("min_size_px")
            if floor is None:
                floor = mobile_floor(str(layer["id"]), variant)
            if floor and layer.get("size_px", 0) < floor:
                failures.append(
                    f"{layer['id']}: {layer['size_px']:.1f}px is below the "
                    f"{floor}px mobile delivery floor at {dest_w}px wide"
                )
    if dest_w != 1080:
        failures.append(f"stage width is {dest_w}, expected 1080")
    expected_h = DELIVERY.get(variant)
    if expected_h and dest_h != expected_h[1]:
        failures.append(f"stage height is {dest_h}, expected {expected_h[1]}")
    return failures


def load_spec(out: Path) -> dict:
    path = out / "spec.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_layers(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "width" not in data or "height" not in data or "layers" not in data:
        sys.exit(f"Error: {path.name} is not a layers.json map (needs width, height, layers).")
    return data


def spec_font_layers(spec: dict) -> list[dict]:
    layers = []
    for path in (spec.get("fonts") or {}).values():
        if path:
            layers.append({"font_file": path, "font_family": Path(path).stem})
    return layers


def convert_variant_from_layers(
    variant: str,
    spec: dict,
    layers_data: dict,
    layers_path: Path,
    wireframe: bool,
) -> dict:
    name = spec.get("output_name") or "ad"
    variant_spec = spec.get("variants", {}).get(variant, {})
    repeated = spec.get("repeated_systems") or variant_spec.get("repeated_systems") or {}
    stem = f"{name}-{variant}"

    if wireframe:
        dest_w, dest_h = DELIVERY.get(variant, (1080, 1350))
        layers = layers_from_spec(variant_spec, dest_w, dest_h)
        zones = image_zones_from_spec(variant_spec, dest_w, dest_h)
        plate_src = ""
        ver = "0"
        sx = sy = 1.0
        centering = None
    else:
        src_w, src_h = layers_data["width"], layers_data["height"]
        dest_w, dest_h = delivery_size(variant or layers_data.get("variant"), src_w, src_h)
        sx, sy = scale_xy(src_w, src_h, dest_w, dest_h)
        layers = [scaled_layer(layer, sx, sy) for layer in layers_data["layers"]]
        plate = Path(layers_data["plate"]) if layers_data.get("plate") else None
        plate_src = plate.name if plate else ""
        ver = _version_of(layers_path)
        zones = image_zones_from_spec(variant_spec, dest_w, dest_h)
        if plate:
            for zone in zones:
                zone["src"] = plate.name
        centering = (variant_spec.get("plate_layout") or {}).get("centering")

    return {
        "variant": variant,
        "dest_w": dest_w,
        "dest_h": dest_h,
        "layers": layers,
        "image_zones": zones,
        "plate_src": plate_src,
        "hide_images": wireframe,
        "repeated_systems": repeated,
        "centering": centering,
        "ver": ver,
        "stem": stem,
        "name": name,
        "sx": sx,
        "sy": sy,
        "failures": preflight(variant, layers, dest_w, dest_h, check_floors=not wireframe),
    }


def html_for(result: dict, faces: list[tuple[str, str, str]]) -> str:
    extra = font_face_css(faces) + repeated_system_css(result["repeated_systems"])
    css = stage_css(result["dest_w"], result["dest_h"], extra)
    body = render_stage(
        result["variant"],
        result["dest_w"],
        result["dest_h"],
        result["layers"],
        result["plate_src"],
        result["image_zones"],
        result["hide_images"],
        result["repeated_systems"],
        result["centering"],
    )
    return wrap_html(f"{result['stem']} {result['dest_w']}x{result['dest_h']}", css, body)


def board_html(results: list[dict], faces: list[tuple[str, str, str]]) -> str:
    extra = font_face_css(faces)
    for result in results:
        extra += repeated_system_css(result["repeated_systems"])
    css = stage_css(1080, 1920, extra)
    items = []
    for result in results:
        stage = render_stage(
            result["variant"],
            result["dest_w"],
            result["dest_h"],
            result["layers"],
            result["plate_src"],
            result["image_zones"],
            result["hide_images"],
            result["repeated_systems"],
            result["centering"],
            id_prefix=result["variant"],
        )
        label = escape(result["variant"])
        items.append(f'<div class="od-board-item"><p>{label}</p>{stage}</div>')
    body = f'<div class="od-board">{"".join(items)}</div>'
    name = results[0]["name"] if results else "board"
    return wrap_html(f"{name} review board", css, body)


def variant_order(spec: dict) -> list[str]:
    declared = list(spec.get("variants", {}))
    preferred = ["feed_4x5", "fullscreen_9x16"]
    ordered = [v for v in preferred if v in declared]
    ordered += [v for v in declared if v not in ordered]
    return ordered or preferred


def resolve_layers_path(out: Path, name: str, variant: str) -> Path | None:
    if "--layers" in sys.argv and _arg("--variant") in {None, variant}:
        return Path(_arg("--layers"))
    return _latest(out, f"{name}-{variant}-layers_v*.json")


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    if not out.is_dir():
        sys.exit(f"Error: {out} is not a directory.")
    spec = load_spec(out)
    name = spec.get("output_name", out.name)
    spec = {**spec, "output_name": name}
    variant = _arg("--variant")
    wireframe = "--wireframe" in sys.argv
    preflight_only = "--preflight" in sys.argv
    want_board = "--board" in sys.argv

    if want_board:
        variants = variant_order(spec)
    elif variant:
        variants = [variant]
    else:
        variants = variant_order(spec)

    results = []
    original_for_fonts = []
    for var in variants:
        if wireframe:
            data, path = {"width": 1080, "height": DELIVERY.get(var, (1080, 1350))[1], "layers": [], "plate": ""}, Path(f"{var}_v0.json")
            result = convert_variant_from_layers(var, spec, data, path, True)
        else:
            path = resolve_layers_path(out, name, var)
            if not path:
                if variant or not want_board:
                    sys.exit(f"Error: no {name}-{var}-layers_vN.json — run compose-text.py first.")
                continue
            data = load_layers(path)
            original_for_fonts.extend(data["layers"])
            result = convert_variant_from_layers(var, spec, data, path, False)
        results.append(result)

    if not results:
        sys.exit("Error: no variants to convert.")

    for result in results:
        for failure in result["failures"]:
            print("  ✗", failure)

    if preflight_only:
        if any(r["failures"] for r in results):
            sys.exit("Error: Open Design preflight failed — fix layout before writing HTML.")
        print("  ✓ preflight passed")
        return

    faces = collect_font_faces(
        original_for_fonts + spec_font_layers(spec),
        out / "od-fonts",
    )

    for result in results:
        html = html_for(result, faces)
        dest = out / f"{result['stem']}-od_v{result['ver']}.html"
        dest.write_text(html, encoding="utf-8")
        print(f"  ✓ {dest.name} ({result['dest_w']}×{result['dest_h']})")

    if want_board:
        if len(results) < 2:
            sys.exit("Error: --board needs both feed_4x5 and fullscreen_9x16 layers.")
        ordered = sorted(results, key=lambda r: 0 if r["variant"] == "feed_4x5" else 1)
        html = board_html(ordered, faces)
        ver = max(int(r["ver"]) for r in ordered)
        dest = out / f"{name}-board_v{ver}.html"
        dest.write_text(html, encoding="utf-8")
        print(f"  ✓ {dest.name}")

    if any(r["failures"] for r in results):
        sys.exit("Error: Open Design preflight failed — treat the HTML as a draft until every check passes.")


if __name__ == "__main__":
    main()
