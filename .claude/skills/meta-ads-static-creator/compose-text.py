#!/usr/bin/env python3
"""
compose-text.py — set a spec.json text variant onto the matching plate in brand fonts.

Usage (from project root):
  python3 .claude/skills/meta-ads-static-creator/compose-text.py brands/[brand]/generation/meta-ads-static-creator/[output-name] --variant feed_4x5 [--plate path]

Writes [name]-[variant]-final_vN.png, [name]-[variant]-text_vN.svg (editable text,
fonts embedded), [name]-[variant]-layers_vN.json. Without --variant it supports
legacy single-ratio specs and names outputs as before.
Free — no network.
"""
import base64, json, sys
from pathlib import Path
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFont

def _latest(out: Path, stem: str):
    c = sorted(out.glob(f"{stem}_v*.png"), key=lambda p: int(p.stem.rsplit("_v", 1)[1]))
    return c[-1] if c else None

def _wrap(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= max_w or not cur: cur = t
            else: lines.append(cur); cur = w
        lines.append(cur)
    return lines


def _mobile_floor(layer_id, variant):
    """Return the delivery-size floor for standard mobile roles, or None."""
    if variant not in {"feed_4x5", "fullscreen_9x16"}:
        return None
    name = layer_id.lower()
    if "legal" in name or "footnote" in name:
        return 20
    if "caption" in name or "subline" in name:
        return 30
    if "stat" in name:
        return 96
    if "headline" in name:
        return 88
    if name in {"price", "cta"}:
        return 34
    if name in {"kicker", "eyebrow", "before", "after", "order", "save", "code"}:
        return 28
    if "old-price" in name:
        return 24
    return None

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    out = Path(sys.argv[1]); spec = json.load(open(out / "spec.json")); name = spec.get("output_name", out.name)
    variant = sys.argv[sys.argv.index("--variant") + 1] if "--variant" in sys.argv else None
    variants = spec.get("variants", {})
    if variant and variant not in variants:
        sys.exit(f"Error: variant '{variant}' is not declared in spec.json variants.")
    variant_spec = variants.get(variant, {})
    stem = f"{name}-{variant}" if variant else name
    plate = Path(sys.argv[sys.argv.index("--plate") + 1]) if "--plate" in sys.argv else _latest(out, f"{stem}-plate")
    if not plate: sys.exit("Error: no plate found — run generate-blank-ad.py first.")
    ver = plate.stem.rsplit("_v", 1)[1]
    im = Image.open(plate).convert("RGB"); W, H = im.size; draw = ImageDraw.Draw(im)
    fonts = spec.get("fonts", {}); layers = []; svg_text = []; warnings = []; floor_failures = []
    for box in variant_spec.get("text", spec.get("text", [])):
        fpath = fonts.get(box.get("font", "body")); text = box["text"]
        if box.get("uppercase"): text = text.upper()
        b = box["box"]; x0, y0, x1, y1 = b["left"] * W, b["top"] * H, b["right"] * W, b["bottom"] * H
        max_w, max_h = x1 - x0, y1 - y0
        size = box.get("size", 0.03) * H; lh = box.get("line_height", 1.15); floor = size * 0.7
        while True:
            font = ImageFont.truetype(fpath, int(size)) if fpath else ImageFont.load_default()
            lines = _wrap(draw, text, font, max_w); block_h = len(lines) * size * lh
            if (block_h <= max_h and all(draw.textlength(l, font=font) <= max_w for l in lines)) or size <= floor: break
            size *= 0.94
        if size <= floor: warnings.append(f"{box['id']}: shrunk to floor — copy or zone too big")
        mobile_floor = box.get("min_size_px", _mobile_floor(box["id"], variant))
        if mobile_floor and size < mobile_floor:
            floor_failures.append(f"{box['id']}: {size:.1f}px is below the {mobile_floor}px mobile delivery floor")
        align, valign = box.get("align", "left"), box.get("valign", "top")
        y = y0 if valign == "top" else (y1 - block_h if valign == "bottom" else y0 + (max_h - block_h) / 2)
        color = box.get("color", "#000000"); fam = Path(fpath).stem if fpath else "sans-serif"
        decoration = box.get("text_decoration", "none")
        try:
            ascent, descent = font.getmetrics()
        except AttributeError:
            ascent, descent = int(size * 0.8), int(size * 0.2)
        rendered_lines = []
        for i, line in enumerate(lines):
            lw = draw.textlength(line, font=font)
            x = x0 if align == "left" else (x1 - lw if align == "right" else x0 + (max_w - lw) / 2)
            draw_y = y + i * size * lh
            bounds = draw.textbbox((x, draw_y), line, font=font)
            draw.text((x, draw_y), line, font=font, fill=color)
            if decoration == "line-through":
                strike_y = bounds[1] + (bounds[3] - bounds[1]) * 0.52
                draw.line((bounds[0], strike_y, bounds[2], strike_y), fill=color, width=max(1, round(size * 0.055)))
            anchor = {"left": "start", "center": "middle", "right": "end"}[align]
            sx = x0 if align == "left" else (x1 if align == "right" else (x0 + x1) / 2)
            decoration_attr = ' text-decoration="line-through"' if decoration == "line-through" else ""
            svg_text.append(f'<text x="{sx:.1f}" y="{draw_y + ascent:.1f}" font-family="{escape(fam)}" font-size="{size:.1f}" fill="{color}" text-anchor="{anchor}"{decoration_attr}>{escape(line)}</text>')
            rendered_lines.append({
                "text": line,
                "draw_x": round(x, 1), "draw_y": round(draw_y, 1),
                "baseline_y": round(draw_y + ascent, 1),
                "advance_px": round(lw, 1),
                "visible_bounds": {"left": round(bounds[0], 1), "top": round(bounds[1], 1),
                                   "right": round(bounds[2], 1), "bottom": round(bounds[3], 1)}
            })
        layers.append({"id": box["id"], "text": text, "font_file": fpath, "font_family": fam, "size_px": round(size, 1),
                       "line_height": lh, "color": color, "text_decoration": decoration,
                       "font_ascent_px": ascent, "font_descent_px": descent,
                       "align": align, "valign": valign,
                       "x": round(x0), "y": round(y0), "w": round(max_w), "h": round(max_h),
                       "lines": lines, "rendered_lines": rendered_lines})
    if floor_failures:
        for failure in floor_failures:
            print("  ✗", failure)
        sys.exit("Error: mobile type floor failed — recompose the variant before exporting.")
    final = out / f"{stem}-final_v{ver}.png"; im.save(final)
    faces = "".join(f"@font-face{{font-family:'{Path(p).stem}';src:url(data:font/ttf;base64,{base64.b64encode(Path(p).read_bytes()).decode()}) format('truetype');}}" for p in set(filter(None, fonts.values())))
    plate_b64 = base64.b64encode(plate.read_bytes()).decode()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
           f'<style>{faces}</style><image id="plate" width="{W}" height="{H}" xlink:href="data:image/png;base64,{plate_b64}"/>'
           f'<g id="text">{"".join(svg_text)}</g></svg>')
    (out / f"{stem}-text_v{ver}.svg").write_text(svg)
    json.dump({"variant": variant, "plate": str(plate), "width": W, "height": H, "layers": layers}, open(out / f"{stem}-layers_v{ver}.json", "w"), indent=2, ensure_ascii=False)
    print(f"  ✓ {final.name}\n  ✓ {stem}-text_v{ver}.svg\n  ✓ {stem}-layers_v{ver}.json")
    for w in warnings: print("  ⚠", w)

if __name__ == "__main__": main()
