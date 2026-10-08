"""fal.ai provider — GPT Image 2.5 Sunburst edit / text-to-image.

The request shape matches the previous generate-blank-ad.py call, except
quality now follows the shared low-default / high-final rule instead of being
hardcoded to high. fal's schema supports auto|low|medium|high|xhigh|max;
this skill only sends low|medium|high.

Schema: https://fal.ai/models/openai/gpt-image-2.5/sunburst/edit/api
"""
from __future__ import annotations

from typing import NoReturn, Optional

import requests

from . import Plan, PlateRequest, PlateResult, ProviderError, QUALITIES
from ._output import fetch_output

NAME = "fal"
ENV_KEY = "FAL_KEY"
EDIT_MODEL = "openai/gpt-image-2.5/sunburst/edit"
TXT2IMG_MODEL = "openai/gpt-image-2.5/sunburst/text-to-image"
DEFAULT_MODEL = EDIT_MODEL

# Output CDN: v3b.fal.media (documented URL form), v3.fal.media / fal.media
# (SDK upload fallbacks), and fal.run app hosts. Subdomains of each are allowed.
OUTPUT_HOSTS = ("fal.media", "fal.run")

SIZE = {
    "1:1": (1024, 1024),
    "3:4": (1152, 1536),
    "4:5": (1229, 1536),
    "4:3": (1536, 1152),
    "9:16": (864, 1536),
    "16:9": (1536, 864),
    "2:3": (1024, 1536),
}


def _model(req: PlateRequest) -> str:
    return req.model or (EDIT_MODEL if req.images else TXT2IMG_MODEL)


def plan(req: PlateRequest) -> Plan:
    if req.quality not in QUALITIES:
        raise ProviderError(
            f"quality must be one of {QUALITIES}; got '{req.quality}'"
        )
    w, h = SIZE.get(req.ratio, (768, 1024))
    prompt = req.prompt + req.no_text_suffix
    payload = {
        "prompt": prompt,
        "image_size": {"width": w, "height": h},
        "num_images": 1,
        "output_format": "png",
        "quality": req.quality,
    }
    if req.images:
        payload["image_urls"] = [str(p) for p in req.images]
    return Plan(
        provider=NAME,
        model=_model(req),
        payload_preview=payload,
        calls=1,
        est_cost_usd=None,
        cost_note=(
            f"fal bills GPT Image 2.5 Sunburst by tokens (image input $8/1M, "
            f"image output $30/1M at the time of writing); quality={req.quality} "
            f"is sent and changes token use. Quote from "
            f"https://fal.ai/models/openai/gpt-image-2.5/sunburst/edit "
            f"(pricing table) before running. Input images and prompt length add cost."
        ),
        prompt_sent=prompt,
    )


def _output_fail(message: str, *, status: Optional[int] = None) -> NoReturn:
    # fal_client.run has already succeeded when we download, so a broken
    # redirect or refused host is billed — same as "no image returned".
    # fal CDN URLs have no 1-hour expiry; status is accepted and ignored.
    raise ProviderError(message, billed=True)


def _download_output(url: str) -> bytes:
    def get(u: str, *, credentials: bool) -> requests.Response:
        # Output CDN GETs never send FAL_KEY; credentials stays unused by design.
        return requests.get(u, timeout=120, allow_redirects=False)

    _url, r = fetch_output(
        url, get=get, allowed=OUTPUT_HOSTS, fail=_output_fail
    )
    return r.content


def generate(
    req: PlateRequest, p: Plan, resume_id: Optional[str] = None
) -> PlateResult:
    if resume_id:
        raise ProviderError(
            "--resume is only supported for the Replicate provider.", billed=False
        )
    try:
        import fal_client
    except ImportError as exc:  # pragma: no cover
        raise ProviderError(
            f"missing dependency '{exc.name}'. pip install -r requirements.txt"
        ) from exc
    try:
        urls = [fal_client.upload_file(str(path)) for path in req.images]
    except Exception as exc:
        raise ProviderError(f"fal upload failed: {exc}", billed=False) from exc
    args = dict(p.payload_preview)
    if urls:
        args["image_urls"] = urls
    try:
        res = fal_client.run(p.model, arguments=args)
    except Exception as exc:
        raise ProviderError(f"fal run failed: {exc}", billed=None) from exc
    img = (res.get("images") or [{}])[0].get("url")
    if not img:
        raise ProviderError("no image returned from FAL.", billed=True)
    data = _download_output(img)
    return PlateResult(data=data, provider=NAME, model=p.model, meta={"url": img})
