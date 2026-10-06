#!/usr/bin/env python3
"""Build a layout-first ratio plate from existing approved photography.

Usage:
  python3 .claude/skills/meta-ads-static-creator/prepare-ratio-plate.py OUTPUT_DIR --variant feed_4x5

The selected spec variant must declare `plate_layout`: a canvas, reusable image
zones, and optional empty UI rectangles. It creates a text-free ratio plate for the
free brand-font compositor; it never contacts an image model.
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps


def _rect(box, width, height):
    return tuple(round(v * (width if i % 2 == 0 else height)) for i, v in enumerate(box))


def _next(out, stem):
    version = 1
    while (out / f"{stem}_v{version}.png").exists():
        version += 1
    return out / f"{stem}_v{version}.png"


def _image_zone(canvas, zone, root):
    x0, y0, x1, y1 = _rect(zone["box"], *canvas.size)
    target_size = (x1 - x0, y1 - y0)
    source = Image.open(root / zone["source"]).convert("RGB")
    crop = zone.get("crop")
    if crop:
        sx0, sy0, sx1, sy1 = _rect(crop, *source.size)
        source = source.crop((sx0, sy0, sx1, sy1))
    fitted = ImageOps.fit(source, target_size, method=Image.Resampling.LANCZOS,
                          centering=tuple(zone.get("centering", [0.5, 0.5])))
    canvas.paste(fitted, (x0, y0))


def main():
    if len(sys.argv) < 4 or "--variant" not in sys.argv:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    variant = sys.argv[sys.argv.index("--variant") + 1]
    spec = json.loads((out / "spec.json").read_text())
    data = spec.get("variants", {}).get(variant)
    if not data or "plate_layout" not in data:
        sys.exit(f"Error: {variant} needs variants.{variant}.plate_layout in spec.json")
    layout = data["plate_layout"]
    width, height = layout["canvas"]
    canvas = Image.new("RGB", (width, height), layout.get("background", "#FFFFFF"))
    for zone in layout.get("image_zones", []):
        _image_zone(canvas, zone, out)
    draw = ImageDraw.Draw(canvas)
    for shape in layout.get("shapes", []):
        if shape.get("type", "rect") != "rect":
            sys.exit(f"Error: unsupported plate shape {shape.get('type')}")
        box = _rect(shape["box"], width, height)
        draw.rectangle(box, fill=shape.get("fill"), outline=shape.get("outline"),
                       width=shape.get("outline_width", 1))
    stem = f"{spec.get('output_name', out.name)}-{variant}-plate"
    path = _next(out, stem)
    canvas.save(path)
    print(f"  ✓ {path.name}")


if __name__ == "__main__":
    main()
