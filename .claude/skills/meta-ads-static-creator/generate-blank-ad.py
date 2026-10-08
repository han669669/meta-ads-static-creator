#!/usr/bin/env python3
"""
generate-blank-ad.py — text-free ad plate (GPT Image 2.5 Sunburst on fal or Replicate).

Usage (from project root):
  python3 .claude/skills/meta-ads-static-creator/generate-blank-ad.py \\
    brands/[brand]/generation/meta-ads-static-creator/[output-name] \\
    --variant feed_4x5 [--provider fal|replicate] [--estimate] \\
    [--quality low|medium|high] [--final] [--resume PREDICTION_ID]

Reads spec.json from the output folder; sends reference (Image 1, optional),
product images and the product scale reference; saves
[output-name]-[variant]-plate_vN.png.

Quality defaults to low for first-pass plates and edits. --final (or
--quality high) is the explicit high-quality final render.

Replicate is the default provider when both keys are set, or when no key is
set. fal is used when only FAL_KEY is set.

--estimate prints the provider, model, quality, payload and cost and exits
WITHOUT any network call (use it for the cost gate). --resume fetches an
existing Replicate prediction instead of paying for a new one. Without
--variant it supports legacy single-ratio specs.
"""
import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageEnhance
except ImportError as exc:
    sys.exit(f"Error: missing dependency '{exc.name}'. pip install -r requirements.txt")

from providers import (
    ENV_KEYS,
    PlateRequest,
    ProviderError,
    billed_label,
    load_provider,
    resolve_provider,
    resolve_quality,
)

NO_TEXT = (
    " Absolutely no typography anywhere in the image except the printed product packaging: "
    "no words, no letters, no numbers, no placeholder text, no lorem ipsum, no lines or "
    "bars that stand in for text. Reserved zones stay clean empty background."
)
_ENV_ALLOW = {"FAL_KEY", "REPLICATE_API_TOKEN", "IMAGE_PROVIDER"}


def _arg(flag, default=None):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith("--"):
        sys.exit(f"Error: {flag} requires a value.")
    return sys.argv[i + 1]


def _is_home(path: Path) -> bool:
    try:
        return path.resolve() == Path.home().resolve()
    except OSError:
        return False


def _project_root() -> Path:
    """Directory that holds the project .env.

    Prefer $CLAUDE_PROJECT_DIR, then the current working directory, then a
    parent of cwd that contains a .claude folder. Never the user's home
    directory: a skill installed under ~/.claude must not load ~/.env.
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        root = Path(env_dir).expanduser()
        if not _is_home(root):
            return root

    cwd = Path.cwd()
    if not _is_home(cwd) and ((cwd / ".env").is_file() or (cwd / ".claude").is_dir()):
        return cwd

    try:
        start = cwd.resolve()
    except OSError:
        start = cwd
    for parent in [start, *start.parents]:
        if _is_home(parent):
            continue
        if (parent / ".claude").is_dir():
            return parent
    return cwd


def _load_env():
    """Load allow-listed keys from the project-root .env only.

    Does not walk parent folders, does not load non-allow-listed keys, and
    never overrides variables already set in the environment. Never reads
    ~/.env.
    """
    root = _project_root()
    if _is_home(root):
        return
    env_path = root / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, _, v = line.partition("=")
        k = k.strip().removeprefix("export ").strip()
        if k in _ENV_ALLOW:
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def _next(out: Path, stem: str) -> Path:
    n = 1
    while True:
        c = out / f"{stem}_v{n}.png"
        try:
            os.close(os.open(c, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
            return c
        except FileExistsError:
            n += 1


def _crop_to(img, aspect):
    """Centre-crop to an exact aspect without resampling when possible."""
    aw, ah = aspect
    w, h = img.size
    if abs(w / h - aw / ah) < 0.005:
        return img
    if w / h < aw / ah:
        tw, th = w, round(w * ah / aw)
    else:
        tw, th = round(h * aw / ah), h
    left = max(0, (w - tw) // 2)
    top = max(0, (h - th) // 2)
    return img.crop((left, top, left + tw, top + th))


def _inputs(spec):
    """Ordered input images, validated exactly as before. Returns (paths, log lines)."""
    paths, log = [], []
    ref = spec.get("reference_image")
    if ref and spec.get("reference_image_for_generation", True):
        if not Path(ref).exists():
            sys.exit(f"Error: reference image not found: {ref}")
        paths.append(Path(ref))
        log.append(f"  Image 1: reference ({Path(ref).name})")
    elif ref:
        log.append(f"  Reference retained for review, omitted from generation ({Path(ref).name})")
    for p in spec.get("product_images", []):
        if not Path(p).exists():
            sys.exit(f"Error: product image not found: {p}")
        paths.append(Path(p))
        log.append(f"  Image {len(paths)}: {Path(p).name}")
    scale_ref = spec.get("product_scale_reference")
    if not scale_ref:
        sys.exit(
            "Error: spec.json requires product_scale_reference: an approved image "
            "of the exact product in hand or on/against a body."
        )
    if not Path(scale_ref).exists():
        sys.exit(f"Error: product scale reference not found: {scale_ref}")
    if (
        ref
        and Path(scale_ref).resolve() == Path(ref).resolve()
        and spec.get("reference_image_for_generation", True)
    ):
        log.append(f"  Product scale reference: covered by reference ({Path(scale_ref).name})")
    else:
        paths.append(Path(scale_ref))
        log.append(f"  Image {len(paths)}: product scale reference ({Path(scale_ref).name})")
    return paths, log


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    spec = json.load(open(out / "spec.json"))
    _load_env()
    name = spec.get("output_name", out.name)
    variant = _arg("--variant")
    variants = spec.get("variants", {})
    if variant and variant not in variants:
        sys.exit(f"Error: variant '{variant}' is not declared in spec.json variants.")
    variant_spec = variants.get(variant, {})
    ratio = variant_spec.get(
        "aspect_ratio",
        {"feed_4x5": "4:5", "fullscreen_9x16": "9:16"}.get(
            variant, spec.get("aspect_ratio", "3:4")
        ),
    )
    prompt = variant_spec.get("plate_prompt", spec["plate_prompt"]).strip()
    paths, log = _inputs(spec)
    label = f"{name}-{variant}" if variant else name

    provider, why = resolve_provider(_arg("--provider"), spec)
    mod = load_provider(provider)
    popts = {
        **spec.get("provider_options", {}).get(provider, {}),
        **variant_spec.get("provider_options", {}).get(provider, {}),
    }
    quality = resolve_quality(
        cli_quality=_arg("--quality"),
        final="--final" in sys.argv,
        spec_quality=popts.get("quality") or spec.get("quality"),
    )
    req = PlateRequest(
        prompt=prompt,
        no_text_suffix=NO_TEXT,
        ratio=ratio,
        images=paths,
        label=label,
        out_dir=out,
        quality=quality,
        model=popts.get("model"),
        options=popts,
    )
    try:
        plan = mod.plan(req)
    except ProviderError as e:
        sys.exit(f"Error: {e}")
    cost = f"${plan.est_cost_usd:.3f}" if plan.est_cost_usd is not None else "see note"
    print("\n".join(log))
    print(f"\n{label} — plate [{ratio}] {plan.provider}:{plan.model} quality={quality} ({why})")
    print(f"  Estimated cost: {cost} for {plan.calls} call. {plan.cost_note}")
    if plan.crop_to:
        print(
            f"  Note: no native {ratio} size on this model; "
            f"the plate is centre-cropped to {ratio} after generation."
        )
    if "--estimate" in sys.argv or "--dry-run" in sys.argv:
        preview = dict(plan.payload_preview)
        preview["prompt"] = preview.get("prompt", "")[:160] + "…"
        print(
            json.dumps(
                {
                    "provider": plan.provider,
                    "model": plan.model,
                    "quality": quality,
                    "est_cost_usd": plan.est_cost_usd,
                    "crop_to": plan.crop_to,
                    "input": preview,
                },
                indent=2,
            )
        )
        return
    if not os.environ.get(ENV_KEYS[provider]):
        have_any = any(os.environ.get(ENV_KEYS[p]) for p in ENV_KEYS)
        if not have_any:
            sys.exit(
                "Error: no image key set. Add REPLICATE_API_TOKEN (recommended) "
                "or FAL_KEY to .env at the project root."
            )
        sys.exit(
            f"Error: {ENV_KEYS[provider]} not found. Add it to .env at the project root."
        )

    try:
        res = mod.generate(req, plan, resume_id=_arg("--resume"))
    except ProviderError as e:
        sys.exit(f"Error ({provider}, {billed_label(e.billed)}): {e}")
    dest = _next(out, f"{label}-plate")
    try:
        dest.write_bytes(res.data)
        with Image.open(dest) as plate:
            plate.load()
            img = plate.convert("RGB")
        if plan.crop_to:
            img = _crop_to(img, plan.crop_to)
        ImageEnhance.Color(img).enhance(0.9).save(dest, format="PNG")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    extra = f", prediction {res.meta['prediction_id']}" if res.meta.get("prediction_id") else ""
    print(f"  ✓ {dest.name} {img.size[0]}x{img.size[1]} (90% saturation{extra})")


if __name__ == "__main__":
    main()
