#!/usr/bin/env python3
"""
generate-blank-ad.py — text-free ad plate (GPT Image 2.5 Sunburst).

Usage (from project root):
  python3 .claude/skills/meta-ads-static-creator/generate-blank-ad.py brands/[brand]/generation/meta-ads-static-creator/[output-name] --variant feed_4x5

Reads spec.json from the output folder; uploads reference (Image 1, optional) and
product images; saves [output-name]-[variant]-plate_vN.png. Without --variant it
supports legacy single-ratio specs and names output as before.
"""
import json, os, sys
from pathlib import Path
try:
    import fal_client, requests
    from PIL import Image, ImageEnhance
except ImportError as exc:
    sys.exit(f"Error: missing dependency '{exc.name}'. pip install -r requirements.txt")

EDIT_MODEL, TXT2IMG_MODEL = "openai/gpt-image-2.5/sunburst/edit", "openai/gpt-image-2.5/sunburst/text-to-image"
_SIZE = {"1:1": (1024, 1024), "3:4": (1152, 1536), "4:5": (1229, 1536), "4:3": (1536, 1152),
         "9:16": (864, 1536), "16:9": (1536, 864), "2:3": (1024, 1536)}
NO_TEXT = (" Absolutely no typography anywhere in the image except the printed product packaging: "
           "no words, no letters, no numbers, no placeholder text, no lorem ipsum, no lines or "
           "bars that stand in for text. Reserved zones stay clean empty background.")

def _load_env():
    if os.environ.get("FAL_KEY"): return
    p = Path.cwd()
    for _ in range(5):
        f = p / ".env"
        if f.exists():
            for line in f.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("="); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return
        p = p.parent

def _next(out: Path, stem: str) -> Path:
    n = 1
    while True:
        c = out / f"{stem}_v{n}.png"
        try:
            os.close(os.open(c, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)); return c
        except FileExistsError: n += 1

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    out = Path(sys.argv[1]); spec = json.load(open(out / "spec.json"))
    _load_env()
    if not os.environ.get("FAL_KEY"): sys.exit("Error: FAL_KEY not found. Add it to .env at the project root.")
    name = spec.get("output_name", out.name)
    variant = sys.argv[sys.argv.index("--variant") + 1] if "--variant" in sys.argv else None
    variants = spec.get("variants", {})
    if variant and variant not in variants:
        sys.exit(f"Error: variant '{variant}' is not declared in spec.json variants.")
    variant_spec = variants.get(variant, {})
    ratio = variant_spec.get("aspect_ratio", {"feed_4x5": "4:5", "fullscreen_9x16": "9:16"}.get(variant, spec.get("aspect_ratio", "3:4")))
    prompt = variant_spec.get("plate_prompt", spec["plate_prompt"]).strip() + NO_TEXT
    urls = []
    ref = spec.get("reference_image")
    if ref and spec.get("reference_image_for_generation", True):
        urls.append(fal_client.upload_file(ref)); print(f"  Image 1: reference ({Path(ref).name})")
    elif ref:
        print(f"  Reference retained for review, omitted from generation ({Path(ref).name})")
    for p in spec.get("product_images", []):
        if not Path(p).exists(): sys.exit(f"Error: product image not found: {p}")
        urls.append(fal_client.upload_file(p)); print(f"  Image {len(urls)}: {Path(p).name}")
    scale_ref = spec.get("product_scale_reference")
    if not scale_ref:
        sys.exit("Error: spec.json requires product_scale_reference: an approved image of the exact product in hand or on/against a body.")
    if not Path(scale_ref).exists(): sys.exit(f"Error: product scale reference not found: {scale_ref}")
    if ref and Path(scale_ref).resolve() == Path(ref).resolve() and spec.get("reference_image_for_generation", True):
        print(f"  Product scale reference: covered by reference ({Path(scale_ref).name})")
    else:
        urls.append(fal_client.upload_file(scale_ref)); print(f"  Image {len(urls)}: product scale reference ({Path(scale_ref).name})")
    w, h = _SIZE.get(ratio, (768, 1024))
    label = f"{name}-{variant}" if variant else name
    print(f"\n{label} — plate [{ratio}] gpt-image-2.5-sunburst")
    res = fal_client.run(EDIT_MODEL if urls else TXT2IMG_MODEL, arguments={
        "prompt": prompt, "image_size": {"width": w, "height": h}, "num_images": 1,
        "output_format": "png", "quality": "high", **({"image_urls": urls} if urls else {})})
    img = (res.get("images") or [{}])[0].get("url")
    if not img: sys.exit("Error: no image returned from FAL.")
    dest = _next(out, f"{label}-plate")
    try:
        dest.write_bytes(requests.get(img, timeout=120).content)
        # Static-ad imagery is consistently desaturated by 10% as a full-plate treatment.
        with Image.open(dest) as plate:
            ImageEnhance.Color(plate).enhance(0.9).save(dest)
    except BaseException: dest.unlink(missing_ok=True); raise
    print(f"  ✓ {dest.name} (90% saturation)")

if __name__ == "__main__": main()
