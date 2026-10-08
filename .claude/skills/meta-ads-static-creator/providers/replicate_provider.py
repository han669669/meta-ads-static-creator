"""Replicate provider — openai/gpt-image-2.5-sunburst via raw HTTP.

Uses `requests` only (no official Replicate client). No network on import or
in plan(); generate() is the paid path.

Auth: REPLICATE_API_TOKEN as Authorization: Bearer. openai_api_key is never sent.
Inputs: Replicate Files API (private), deleted after the run.
Outputs: downloaded immediately; only from Replicate-owned hosts.
Output GETs start without the API token; a 401/403 retries with the token.

Sources (checked 2026-10-06):
  HTTP API ............ https://replicate.com/docs/reference/http
  Sync mode / deadlines https://replicate.com/docs/topics/predictions/create-a-prediction
  Files API ........... https://api.replicate.com/openapi.json
  Retention ........... https://replicate.com/docs/topics/predictions/data-retention
  Model schema ........ https://replicate.com/openai/gpt-image-2.5-sunburst/api/schema
"""
from __future__ import annotations

import mimetypes
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, Tuple

import requests

from . import Plan, PlateRequest, PlateResult, ProviderError, QUALITIES
from ._output import fetch_output, hostname

NAME = "replicate"
ENV_KEY = "REPLICATE_API_TOKEN"
DEFAULT_MODEL = "openai/gpt-image-2.5-sunburst"
API = "https://api.replicate.com/v1"  # not overridable (token-exfiltration risk)
PRICES_CHECKED = "2026-10-06"
PRICES = {"low": 0.012, "medium": 0.047, "high": 0.128}
PRICE_PAGE = (
    f"https://replicate.com/{DEFAULT_MODEL}#pricing (checked {PRICES_CHECKED})"
)

TERMINAL = {"succeeded", "failed", "canceled", "aborted"}
SYNC_WAIT_S = 60
CANCEL_AFTER = "15m"
POLL_EVERY_S = 2.0
POLL_DEADLINE_S = 16 * 60
# Output files: replicate.delivery and its subdomains. Authenticated Files API
# URLs live on api.replicate.com. Do not allow the rest of replicate.com.
OUTPUT_HOSTS = ("replicate.delivery", "api.replicate.com")
POLL_URL_PREFIX = f"{API}/predictions/"

# ratio -> (aspect_ratio enum value, crop_to). 4:5 is not native: generate
# 1152x1536 (3:4) and centre-crop to 1152x1440. 9:16 is native at 1152x2048.
_SIZE = {
    "1:1": ("1024x1024", None),
    "2:3": ("1024x1536", None),
    "3:2": ("1536x1024", None),
    "3:4": ("1152x1536", None),
    "4:3": ("1536x1152", None),
    "4:5": ("1152x1536", (4, 5)),
    "5:4": ("1536x1152", (5, 4)),
    "9:16": ("1152x2048", None),
    "16:9": ("2048x1152", None),
}


def _model(req: PlateRequest) -> str:
    model = req.model or req.options.get("model") or DEFAULT_MODEL
    if model != DEFAULT_MODEL:
        raise ProviderError(
            f"Replicate path uses {DEFAULT_MODEL} only; got '{model}'."
        )
    return model


def _build(
    req: PlateRequest, model: str, images: List[Any]
) -> Tuple[Dict[str, Any], Optional[Tuple[int, int]], float, str, str]:
    if req.quality not in QUALITIES:
        raise ProviderError(
            f"{model} quality must be one of {QUALITIES}; got '{req.quality}'"
        )
    if req.ratio not in _SIZE:
        raise ProviderError(f"{model}: no size mapping for ratio {req.ratio}")
    size, crop = _SIZE[req.ratio]
    prompt = req.prompt + req.no_text_suffix
    if crop:
        prompt += (
            f" Compose for a {req.ratio} frame: keep every important element "
            f"inside the central {req.ratio} area, because the outer edges of "
            f"this taller canvas will be trimmed."
        )
    inp: Dict[str, Any] = {
        "prompt": prompt,
        "aspect_ratio": size,
        "quality": req.quality,
        "number_of_images": 1,
        "output_format": "png",
    }
    if images:
        inp["input_images"] = list(images)
    cost = PRICES[req.quality]
    note = (
        f"${cost:.3f} per output image at quality={req.quality}; "
        f"input images not billed. {PRICE_PAGE}"
    )
    return inp, crop, round(cost, 4), note, prompt


def plan(req: PlateRequest) -> Plan:
    """Pure function: no network. Used for --estimate and the cost gate."""
    model = _model(req)
    inp, crop, cost, note, prompt = _build(req, model, [str(p) for p in req.images])
    return Plan(
        provider=NAME,
        model=model,
        payload_preview=inp,
        calls=1,
        est_cost_usd=cost,
        cost_note=note,
        crop_to=crop,
        prompt_sent=prompt,
    )


def _session() -> requests.Session:
    token = os.environ.get(ENV_KEY, "").strip()
    if not token:
        raise ProviderError(f"{ENV_KEY} not found. Add it to .env at the project root.")
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "User-Agent": "meta-ads-static-creator/replicate",
    })
    return s


def _detail(r: requests.Response) -> str:
    try:
        body = r.json()
        return str(body.get("detail") or body.get("title") or body)
    except ValueError:
        return r.text[:300]


def _retry_after(r: requests.Response, fallback: float) -> float:
    raw = r.headers.get("Retry-After")
    if not raw:
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback


def _get(s: requests.Session, url: str, *, tries: int = 5, **kw: Any) -> requests.Response:
    """GETs are free and idempotent: retry network errors, 429 and 5xx."""
    timeout = kw.pop("timeout", 60)
    delay = 1.0
    last_error: Optional[BaseException] = None
    for attempt in range(tries):
        try:
            r = s.get(url, timeout=timeout, **kw)
            if r.status_code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                return r
            delay = _retry_after(r, delay)
        except requests.RequestException as exc:
            last_error = exc
            if attempt == tries - 1:
                raise
        time.sleep(min(delay, 30))
        delay *= 2
    if last_error:
        raise last_error
    raise ProviderError("GET retries exhausted")


def _upload(s: requests.Session, path: Path) -> Tuple[str, Optional[str]]:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as fh:
        r = s.post(
            f"{API}/files",
            files={"content": (path.name, fh, mime)},
            timeout=(10, 300),
        )
    if r.status_code != 201:
        raise ProviderError(
            f"file upload failed for {path.name}: HTTP {r.status_code} {_detail(r)}",
            billed=False,
        )
    body = r.json()
    return body["urls"]["get"], body.get("id")


def _delete_files(s: requests.Session, ids: List[str]) -> None:
    for fid in ids:
        try:
            s.delete(f"{API}/files/{fid}", timeout=30)
        except Exception:
            pass


def _find_recent(
    s: requests.Session, model: str, prompt: str
) -> Optional[Dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        r = _get(s, f"{API}/predictions", params={"created_after": since})
        for pred in r.json().get("results", []) if r.ok else []:
            if pred.get("model") == model and (pred.get("input") or {}).get("prompt") == prompt:
                return pred
    except Exception:
        return None
    return None


def _create(s: requests.Session, model: str, inp: Dict[str, Any]) -> Dict[str, Any]:
    """POST once. Only a 429 (nothing created) is retried."""
    url = f"{API}/models/{model}/predictions"
    headers = {"Prefer": "wait", "Cancel-After": CANCEL_AFTER}
    for attempt in range(3):
        try:
            r = s.post(
                url,
                json={"input": inp},
                headers=headers,
                timeout=(10, SYNC_WAIT_S + 15),
            )
        except requests.Timeout:
            found = _find_recent(s, model, inp["prompt"])
            if found:
                print(f"  ↻ request timed out; resuming prediction {found['id']}")
                return found
            raise ProviderError(
                "create request timed out and no matching prediction was found. "
                "Check https://replicate.com/predictions before re-running.",
                billed=None,
            )
        if r.status_code == 429 and attempt < 2:
            time.sleep(_retry_after(r, 30))
            continue
        if r.status_code not in (200, 201, 202):
            raise ProviderError(
                f"Replicate rejected the request: HTTP {r.status_code} {_detail(r)}",
                billed=False,
            )
        return r.json()
    raise ProviderError("rate limited by Replicate (HTTP 429) after retries", billed=False)


def _wait(
    s: requests.Session, pred: Dict[str, Any], label: str, out_dir: Path
) -> Dict[str, Any]:
    marker = out_dir / f".{label}-replicate-pending.txt"
    marker.write_text(f"{pred['id']}\n{pred.get('urls', {}).get('web', '')}\n")
    deadline = time.monotonic() + POLL_DEADLINE_S
    while pred.get("status") not in TERMINAL and not (
        pred.get("output") and pred.get("status") == "processing"
    ):
        if time.monotonic() > deadline:
            raise ProviderError(
                f"prediction {pred['id']} still {pred.get('status')} after 16 min; "
                f"see {pred.get('urls', {}).get('web')}",
                billed=None,
                prediction_id=pred["id"],
            )
        time.sleep(POLL_EVERY_S)
        r = _get(s, _prediction_poll_url(pred))
        if r.ok:
            pred = r.json()
    return pred


def _prediction_poll_url(pred: Dict[str, Any]) -> str:
    """Poll only Replicate's predictions endpoint, never a caller-supplied host."""
    url = (pred.get("urls") or {}).get("get") or ""
    if not isinstance(url, str) or not url.startswith(POLL_URL_PREFIX):
        raise ProviderError(
            f"refusing to poll prediction at unexpected URL {url!r}; "
            f"expected a URL starting with {POLL_URL_PREFIX}"
        )
    return url


def _plain_session() -> requests.Session:
    """Unauthenticated session for output GETs. No API token."""
    return requests.Session()


def _output_fail(message: str) -> NoReturn:
    # Called only from _download after a succeeded prediction, so billed.
    raise ProviderError(message, billed=True)


def _get_output(s: requests.Session, url: str, *, timeout: int) -> requests.Response:
    return _get(s, url, timeout=timeout, allow_redirects=False)


def _first_url(output: Any) -> Optional[str]:
    if isinstance(output, str):
        return output
    if isinstance(output, list) and output and isinstance(output[0], str):
        return output[0]
    if isinstance(output, dict):
        for v in output.values():
            url = _first_url(v)
            if url:
                return url
    return None


def _download(s: requests.Session, url: str) -> bytes:
    timeout = 120
    # replicate.delivery URLs are often public. Use the same retry/backoff as
    # other GETs, but without the API token. The HTTP API still documents
    # Authorization for some file URLs, so retry with the token only on 401/403
    # and only after the host allow-list above. Redirects are followed by hand
    # so a 3xx cannot land on an unchecked host with the Bearer token.
    plain = _plain_session()

    def get(u: str, *, credentials: bool) -> requests.Response:
        return _get_output(s if credentials else plain, u, timeout=timeout)

    url, r = fetch_output(
        url, get=get, allowed=OUTPUT_HOSTS, fail=_output_fail
    )
    if r.status_code in (401, 403):
        url, r = fetch_output(
            url,
            get=get,
            allowed=OUTPUT_HOSTS,
            fail=_output_fail,
            auth_host=hostname(url),
        )
    if not r.ok:
        raise ProviderError(
            f"output download failed: HTTP {r.status_code}. URLs expire after 1 hour.",
            billed=True,
        )
    return r.content


def generate(
    req: PlateRequest, p: Plan, resume_id: Optional[str] = None
) -> PlateResult:
    s = _session()
    file_ids: List[str] = []
    marker = req.out_dir / f".{req.label}-replicate-pending.txt"
    t0 = time.monotonic()
    try:
        if resume_id:
            r = _get(s, f"{API}/predictions/{resume_id}")
            if not r.ok:
                raise ProviderError(
                    f"cannot fetch prediction {resume_id}: HTTP {r.status_code} {_detail(r)}"
                )
            pred = r.json()
        else:
            urls = []
            for path in req.images:
                url, fid = _upload(s, Path(path))
                urls.append(url)
                if fid:
                    file_ids.append(fid)
            inp, _, _, _, _ = _build(req, p.model, urls)
            if "openai_api_key" in inp:
                raise ProviderError("internal error: openai_api_key must never be sent")
            pred = _create(s, p.model, inp)
        pred = _wait(s, pred, req.label, req.out_dir)
        status = pred.get("status")
        if status in ("failed", "aborted"):
            raise ProviderError(
                f"prediction {pred['id']} {status}: {pred.get('error')}",
                billed=False,
                prediction_id=pred["id"],
            )
        if status == "canceled":
            raise ProviderError(
                f"prediction {pred['id']} canceled (deadline {CANCEL_AFTER}); "
                "canceled official-model runs may still be charged.",
                billed=None,
                prediction_id=pred["id"],
            )
        url = _first_url(pred.get("output"))
        if not url:
            raise ProviderError(
                f"prediction {pred['id']} returned no image "
                f"(data_removed={pred.get('data_removed')})",
                billed=True,
                prediction_id=pred["id"],
            )
        data = _download(s, url)
        marker.unlink(missing_ok=True)
        return PlateResult(
            data=data,
            provider=NAME,
            model=p.model,
            meta={
                "prediction_id": pred["id"],
                "web": pred.get("urls", {}).get("web"),
                "predict_time": (pred.get("metrics") or {}).get("predict_time"),
                "wall_s": round(time.monotonic() - t0, 1),
            },
        )
    finally:
        _delete_files(s, file_ids)
