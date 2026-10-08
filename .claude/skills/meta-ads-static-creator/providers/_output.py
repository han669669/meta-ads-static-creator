"""HTTPS, host allow-list, and redirect chasing for output downloads.

Providers pass their allow-list, a GET function, and an error callback.
This module holds no API tokens. `get(url, *, credentials=...)` is how a
caller sends (or withholds) a credential header. Credentials are allowed
only for the same allow-listed host that was authenticated (`auth_host`).

Used after the paid generate: Replicate downloads only once a prediction
has succeeded, and fal downloads only once `fal_client.run` has returned
an image URL. Failures raised through `fail` should be `billed=True` —
including an empty redirect `Location`, a non-OK final response, and a
timeout or connection error from `get` — because the generation has
already happened.

No network on import. `get` must not follow redirects.
"""
from __future__ import annotations

from typing import Any, Callable, NoReturn, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

import requests

MAX_REDIRECTS = 5
REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})

Fail = Callable[[str], NoReturn]
Get = Callable[..., Any]


def hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def host_allowed(host: str, allowed: Sequence[str]) -> bool:
    host = (host or "").lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def check_output_url(url: str, allowed: Sequence[str], *, fail: Fail) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        fail(f"refusing to download output from non-HTTPS URL ({parsed.scheme})")
    host = parsed.hostname or ""
    if not host_allowed(host, allowed):
        fail(f"refusing to download output from unexpected host {host}")


def redirect_target(current: str, location: str, *, fail: Fail) -> str:
    loc = (location or "").strip()
    if not loc:
        fail("refusing redirect with empty Location")
    return urljoin(current, loc)


def credentials_allowed_for_hop(
    url: str, *, auth_host: Optional[str], allowed: Sequence[str]
) -> bool:
    """Send credentials only to the same allow-listed host that was authenticated."""
    if not auth_host:
        return False
    host = hostname(url)
    if host != auth_host.lower():
        return False
    return host_allowed(host, allowed)


def _is_ok(response: Any) -> bool:
    return 200 <= int(response.status_code) < 300


def _call_get(get: Get, url: str, *, credentials: bool, fail: Fail) -> Any:
    try:
        return get(url, credentials=credentials)
    except requests.RequestException as exc:
        fail(f"output download failed: {exc}")


def fetch_output(
    url: str,
    *,
    get: Get,
    allowed: Sequence[str],
    fail: Fail,
    auth_host: Optional[str] = None,
    max_hops: int = MAX_REDIRECTS,
    passthrough: Sequence[int] = (),
) -> Tuple[str, Any]:
    """GET `url`, then follow 3xx hops with HTTPS + allow-list checks.

    Each hop calls `get(url, credentials=...)`. Credentials are True only
    when `auth_host` is set and the hop is that same allow-listed host.

    A non-OK final status is passed to `fail`, except statuses in
    `passthrough` (Replicate uses 401/403 so it can retry with the token).
    `requests.RequestException` from `get` (timeout, connection error) is
    also passed to `fail`.
    """
    check_output_url(url, allowed, fail=fail)
    r = _call_get(
        get,
        url,
        credentials=credentials_allowed_for_hop(
            url, auth_host=auth_host, allowed=allowed
        ),
        fail=fail,
    )
    hops = 0
    while r.status_code in REDIRECT_STATUS:
        hops += 1
        if hops > max_hops:
            fail(f"too many redirects while downloading output (>{max_hops})")
        nxt = redirect_target(url, r.headers.get("Location") or "", fail=fail)
        check_output_url(nxt, allowed, fail=fail)
        r = _call_get(
            get,
            nxt,
            credentials=credentials_allowed_for_hop(
                nxt, auth_host=auth_host, allowed=allowed
            ),
            fail=fail,
        )
        url = nxt
    if r.status_code not in passthrough and not _is_ok(r):
        fail(f"output download failed: HTTP {r.status_code}")
    return url, r
