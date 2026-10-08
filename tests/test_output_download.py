"""Offline tests for providers._output. No network."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import requests

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "meta-ads-static-creator"
sys.path.insert(0, str(SKILL))

from providers import ProviderError  # noqa: E402
from providers import _output as out  # noqa: E402


class FakeResp:
    def __init__(self, status, content=b"", headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}
        self.ok = 200 <= status < 300


def _fail(message: str) -> None:
    raise ProviderError(message, billed=True)


class HostAllowTests(unittest.TestCase):
    def test_exact_and_subdomain(self):
        allowed = ("fal.media", "fal.run")
        self.assertTrue(out.host_allowed("fal.media", allowed))
        self.assertTrue(out.host_allowed("v3b.fal.media", allowed))
        self.assertTrue(out.host_allowed("queue.fal.run", allowed))
        self.assertFalse(out.host_allowed("fal.media.evil.com", allowed))
        self.assertFalse(out.host_allowed("evil.com", allowed))
        self.assertFalse(out.host_allowed("", allowed))

    def test_replicate_hosts(self):
        allowed = ("replicate.delivery", "api.replicate.com")
        self.assertTrue(out.host_allowed("pbxt.replicate.delivery", allowed))
        self.assertTrue(out.host_allowed("api.replicate.com", allowed))
        self.assertFalse(out.host_allowed("replicate.com", allowed))


class CheckUrlTests(unittest.TestCase):
    def test_https_ok(self):
        out.check_output_url(
            "https://v3.fal.media/x.png", ("fal.media",), fail=_fail
        )

    def test_rejects_http(self):
        with self.assertRaises(ProviderError) as cm:
            out.check_output_url("http://fal.media/x.png", ("fal.media",), fail=_fail)
        self.assertIn("non-HTTPS", str(cm.exception))
        self.assertIs(cm.exception.billed, True)

    def test_rejects_foreign_host(self):
        with self.assertRaises(ProviderError) as cm:
            out.check_output_url(
                "https://evil.example.com/x.png", ("fal.media",), fail=_fail
            )
        self.assertIn("unexpected host", str(cm.exception))
        self.assertIs(cm.exception.billed, True)


class RedirectTargetTests(unittest.TestCase):
    def test_absolute_and_relative(self):
        self.assertEqual(
            out.redirect_target(
                "https://v3b.fal.media/files/b/x/out.png",
                "https://v3.fal.media/files/out.png",
                fail=_fail,
            ),
            "https://v3.fal.media/files/out.png",
        )
        self.assertEqual(
            out.redirect_target(
                "https://v3b.fal.media/files/b/x/out.png",
                "/files/out.png",
                fail=_fail,
            ),
            "https://v3b.fal.media/files/out.png",
        )

    def test_empty_location_is_billed(self):
        with self.assertRaises(ProviderError) as cm:
            out.redirect_target("https://fal.media/x", "", fail=_fail)
        self.assertIn("empty Location", str(cm.exception))
        self.assertIs(cm.exception.billed, True)


class CredentialPolicyTests(unittest.TestCase):
    allowed = ("replicate.delivery", "api.replicate.com")

    def test_same_allowlisted_host_only(self):
        self.assertTrue(
            out.credentials_allowed_for_hop(
                "https://replicate.delivery/y.png",
                auth_host="replicate.delivery",
                allowed=self.allowed,
            )
        )
        self.assertFalse(
            out.credentials_allowed_for_hop(
                "https://api.replicate.com/v1/files/f1",
                auth_host="replicate.delivery",
                allowed=self.allowed,
            )
        )
        self.assertFalse(
            out.credentials_allowed_for_hop(
                "https://replicate.delivery/y.png",
                auth_host=None,
                allowed=self.allowed,
            )
        )
        self.assertFalse(
            out.credentials_allowed_for_hop(
                "https://evil.example.com/x",
                auth_host="evil.example.com",
                allowed=self.allowed,
            )
        )


class FetchOutputTests(unittest.TestCase):
    allowed = ("replicate.delivery", "api.replicate.com")

    def test_follows_relative_redirect(self):
        calls = []

        def get(url, *, credentials):
            calls.append((url, credentials))
            if url.endswith("/x.png"):
                return FakeResp(302, headers={"Location": "/y.png"})
            return FakeResp(200, content=b"img")

        url, r = out.fetch_output(
            "https://replicate.delivery/x.png",
            get=get,
            allowed=self.allowed,
            fail=_fail,
        )
        self.assertEqual(url, "https://replicate.delivery/y.png")
        self.assertEqual(r.content, b"img")
        self.assertEqual(
            calls,
            [
                ("https://replicate.delivery/x.png", False),
                ("https://replicate.delivery/y.png", False),
            ],
        )

    def test_does_not_get_foreign_redirect_target(self):
        calls = []

        def get(url, *, credentials):
            calls.append(url)
            return FakeResp(
                302, headers={"Location": "https://evil.example.com/x.png"}
            )

        with self.assertRaises(ProviderError) as cm:
            out.fetch_output(
                "https://replicate.delivery/start.png",
                get=get,
                allowed=self.allowed,
                fail=_fail,
            )
        self.assertIn("unexpected host", str(cm.exception))
        self.assertEqual(calls, ["https://replicate.delivery/start.png"])

    def test_drops_credentials_when_host_changes(self):
        calls = []

        def get(url, *, credentials):
            calls.append((url, credentials))
            if "replicate.delivery" in url:
                return FakeResp(
                    302,
                    headers={"Location": "https://api.replicate.com/v1/files/f1"},
                )
            return FakeResp(200, content=b"img")

        url, r = out.fetch_output(
            "https://replicate.delivery/x.png",
            get=get,
            allowed=self.allowed,
            fail=_fail,
            auth_host="replicate.delivery",
        )
        self.assertEqual(r.content, b"img")
        self.assertEqual(calls[0], ("https://replicate.delivery/x.png", True))
        self.assertEqual(calls[1][0], "https://api.replicate.com/v1/files/f1")
        self.assertFalse(calls[1][1])
        self.assertEqual(url, "https://api.replicate.com/v1/files/f1")

    def test_keeps_credentials_on_same_host(self):
        calls = []

        def get(url, *, credentials):
            calls.append((url, credentials))
            if url.endswith("/x.png"):
                return FakeResp(
                    302, headers={"Location": "https://replicate.delivery/y.png"}
                )
            return FakeResp(200, content=b"img")

        out.fetch_output(
            "https://replicate.delivery/x.png",
            get=get,
            allowed=self.allowed,
            fail=_fail,
            auth_host="replicate.delivery",
        )
        self.assertTrue(all(credentials for _url, credentials in calls))
        self.assertEqual(len(calls), 2)

    def test_too_many_hops(self):
        def get(url, *, credentials):
            return FakeResp(
                302, headers={"Location": "https://replicate.delivery/next.png"}
            )

        with self.assertRaises(ProviderError) as cm:
            out.fetch_output(
                "https://replicate.delivery/start.png",
                get=get,
                allowed=self.allowed,
                fail=_fail,
            )
        self.assertIn("too many redirects", str(cm.exception))
        self.assertIn(f">{out.MAX_REDIRECTS}", str(cm.exception))
        self.assertIs(cm.exception.billed, True)

    def test_non_ok_final_status_is_failed(self):
        def get(url, *, credentials):
            return FakeResp(503)

        with self.assertRaises(ProviderError) as cm:
            out.fetch_output(
                "https://replicate.delivery/x.png",
                get=get,
                allowed=self.allowed,
                fail=_fail,
            )
        self.assertIn("HTTP 503", str(cm.exception))
        self.assertIs(cm.exception.billed, True)

    def test_passthrough_returns_401_without_failing(self):
        def get(url, *, credentials):
            return FakeResp(401)

        url, r = out.fetch_output(
            "https://replicate.delivery/x.png",
            get=get,
            allowed=self.allowed,
            fail=_fail,
            passthrough=(401, 403),
        )
        self.assertEqual(r.status_code, 401)
        self.assertEqual(url, "https://replicate.delivery/x.png")

    def test_timeout_is_failed(self):
        def get(url, *, credentials):
            raise requests.Timeout("timed out")

        with self.assertRaises(ProviderError) as cm:
            out.fetch_output(
                "https://replicate.delivery/x.png",
                get=get,
                allowed=self.allowed,
                fail=_fail,
            )
        self.assertIn("output download failed", str(cm.exception))
        self.assertIs(cm.exception.billed, True)


if __name__ == "__main__":
    unittest.main()

