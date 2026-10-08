"""Offline tests for the Replicate provider. No network: requests.Session is mocked.

Run from the repo root:
  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
from PIL import Image

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "meta-ads-static-creator"
SCRIPT = SKILL / "generate-blank-ad.py"
sys.path.insert(0, str(SKILL))

from providers import (  # noqa: E402
    PlateRequest,
    ProviderError,
    resolve_provider,
    resolve_quality,
)
from providers import replicate_provider as rp  # noqa: E402
from providers import fal_provider as fp  # noqa: E402


def _png(path, size=(64, 80), color=(200, 30, 30)):
    Image.new("RGB", size, color).save(path)
    return path


def _png_bytes(size):
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _load_script():
    spec = importlib.util.spec_from_file_location("generate_blank_ad", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _record_gets(session, handler):
    """Replace session.get while keeping Session.headers on each recorded call."""
    recorded = []

    def get(url, **kw):
        headers = {**dict(session.headers), **(kw.get("headers") or {})}
        recorded.append(
            {
                "url": url,
                "headers": headers,
                "allow_redirects": kw.get("allow_redirects"),
                "timeout": kw.get("timeout"),
            }
        )
        return handler(url, kw, headers)

    session.get = get
    return recorded


class FakeResp:
    def __init__(self, status, body=None, content=b"", headers=None):
        self.status_code = status
        self._body = body
        self.content = content
        self.headers = headers or {}
        self.ok = 200 <= status < 300
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.imgs = [
            _png(self.tmp / "ref.png"),
            _png(self.tmp / "pack.png"),
            _png(self.tmp / "hand.png"),
        ]

    def req(self, **kw):
        base = dict(
            prompt="Plate prompt.",
            no_text_suffix=" NO TEXT.",
            ratio="4:5",
            images=self.imgs,
            label="t-feed_4x5",
            out_dir=self.tmp,
        )
        base.update(kw)
        return PlateRequest(**base)

    def test_sunburst_45_maps_to_3x4_and_crops(self):
        p = rp.plan(self.req())
        self.assertEqual(p.model, "openai/gpt-image-2.5-sunburst")
        i = p.payload_preview
        self.assertEqual(i["aspect_ratio"], "1152x1536")
        self.assertEqual(p.crop_to, (4, 5))
        self.assertEqual(i["quality"], "low")
        self.assertEqual(i["output_format"], "png")
        self.assertEqual(i["number_of_images"], 1)
        self.assertEqual(len(i["input_images"]), 3)
        self.assertNotIn("openai_api_key", i)
        self.assertAlmostEqual(p.est_cost_usd, 0.012)

    def test_sunburst_916_native(self):
        p = rp.plan(self.req(ratio="9:16"))
        self.assertEqual(p.payload_preview["aspect_ratio"], "1152x2048")
        self.assertIsNone(p.crop_to)

    def test_high_quality_price(self):
        p = rp.plan(self.req(quality="high"))
        self.assertEqual(p.payload_preview["quality"], "high")
        self.assertAlmostEqual(p.est_cost_usd, 0.128)

    def test_medium_quality_price(self):
        p = rp.plan(self.req(quality="medium"))
        self.assertAlmostEqual(p.est_cost_usd, 0.047)

    def test_bad_quality_rejected(self):
        with self.assertRaises(ProviderError):
            rp.plan(self.req(quality="xhigh"))

    def test_other_replicate_model_rejected(self):
        with self.assertRaises(ProviderError):
            rp.plan(self.req(model="google/nano-banana-pro"))

    def test_fal_sends_same_quality(self):
        p = fp.plan(self.req(quality="low"))
        self.assertEqual(p.payload_preview["quality"], "low")
        self.assertEqual(p.payload_preview["output_format"], "png")
        self.assertIsNone(p.est_cost_usd)
        self.assertEqual(p.payload_preview["image_size"], {"width": 1229, "height": 1536})


class QualityResolveTests(unittest.TestCase):
    def test_default_is_low(self):
        self.assertEqual(resolve_quality(), "low")

    def test_final_is_high(self):
        self.assertEqual(resolve_quality(final=True), "high")

    def test_cli_quality_wins_over_final(self):
        self.assertEqual(resolve_quality(cli_quality="medium", final=True), "medium")

    def test_spec_quality(self):
        self.assertEqual(resolve_quality(spec_quality="high"), "high")

    def test_final_wins_over_spec(self):
        self.assertEqual(resolve_quality(final=True, spec_quality="low"), "high")

    def test_invalid_quality_exits(self):
        with self.assertRaises(SystemExit):
            resolve_quality(cli_quality="ultra")


class CropTests(unittest.TestCase):
    def test_centre_crop_1152x1536_to_4x5(self):
        gba = _load_script()
        img = Image.new("RGB", (1152, 1536), (0, 0, 0))
        img.putpixel((0, 0), (255, 0, 0))
        img.putpixel((1151, 1535), (0, 255, 0))
        cropped = gba._crop_to(img, (4, 5))
        self.assertEqual(cropped.size, (1152, 1440))


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.imgs = [_png(self.tmp / "pack.png"), _png(self.tmp / "hand.png")]
        os.environ["REPLICATE_API_TOKEN"] = "r8_test_not_real"
        rp.POLL_EVERY_S = 0
        self.sleep = mock.patch.object(rp.time, "sleep")
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        self.req = PlateRequest(
            prompt="P.",
            no_text_suffix=" N.",
            ratio="9:16",
            images=self.imgs,
            label="t-fullscreen_9x16",
            out_dir=self.tmp,
        )

    def _session(self, create_resp, polls, download):
        s = mock.MagicMock()
        file_n = iter(range(100))

        def post(url, **kw):
            if url.endswith("/files"):
                n = next(file_n)
                return FakeResp(
                    201,
                    {"id": f"f{n}", "urls": {"get": f"https://api.replicate.com/v1/files/f{n}"}},
                )
            self.sent = kw["json"]
            self.sent_headers = kw["headers"]
            if callable(create_resp):
                return create_resp()
            return create_resp

        s.post.side_effect = post
        seq = iter(polls)

        def get(url, **kw):
            # Authenticated retry path. The first output GET uses _plain_session.
            if download is not None and (
                "replicate.delivery" in url or url.startswith("https://api.replicate.com/v1/files/")
            ):
                return download
            return next(seq)

        s.get.side_effect = get
        return s

    def _run_generate(self, s, *, download=None, resume_id=None, req=None):
        if download is None:
            download = FakeResp(200, content=_png_bytes((64, 64)))
        req = req or self.req
        plain = rp._plain_session()
        plain.get = mock.Mock(return_value=download)
        with mock.patch.object(rp, "_session", return_value=s):
            with mock.patch.object(rp, "_plain_session", return_value=plain):
                self.plain = plain
                return rp.generate(req, rp.plan(req), resume_id=resume_id)

    def test_happy_path_with_polling(self):
        pred = {
            "id": "p1",
            "status": "starting",
            "output": None,
            "urls": {
                "get": "https://api.replicate.com/v1/predictions/p1",
                "web": "https://replicate.com/p/p1",
            },
        }
        done = dict(
            pred,
            status="succeeded",
            output=["https://replicate.delivery/xezq/abc/out.png"],
            metrics={"predict_time": 31.2},
        )
        s = self._session(
            FakeResp(201, pred),
            [FakeResp(200, dict(pred, status="processing")), FakeResp(200, done)],
            None,
        )
        res = self._run_generate(
            s, download=FakeResp(200, content=_png_bytes((1152, 2048)))
        )
        self.assertEqual(res.meta["prediction_id"], "p1")
        self.plain.get.assert_called()
        self.assertEqual(self.plain.get.call_args.kwargs.get("timeout"), 120)
        self.assertEqual(self.plain.get.call_args.kwargs.get("allow_redirects"), False)
        self.assertNotIn("Authorization", self.plain.get.call_args.kwargs.get("headers") or {})
        self.assertNotIn("Authorization", dict(self.plain.headers))
        delivery_gets = [
            c for c in s.get.call_args_list if c.args and "replicate.delivery" in c.args[0]
        ]
        self.assertEqual(len(delivery_gets), 0)
        self.assertEqual(
            self.sent["input"]["input_images"],
            ["https://api.replicate.com/v1/files/f0", "https://api.replicate.com/v1/files/f1"],
        )
        self.assertEqual(self.sent["input"]["output_format"], "png")
        self.assertEqual(self.sent["input"]["quality"], "low")
        self.assertNotIn("openai_api_key", self.sent["input"])
        self.assertEqual(self.sent_headers["Prefer"], "wait")
        self.assertEqual(self.sent_headers["Cancel-After"], "15m")
        self.assertEqual(s.delete.call_count, 2)
        self.assertFalse((self.tmp / ".t-fullscreen_9x16-replicate-pending.txt").exists())

    def test_failed_prediction_reports_not_billed(self):
        pred = {
            "id": "p2",
            "status": "failed",
            "error": "moderation",
            "output": None,
            "urls": {"get": "https://api.replicate.com/v1/predictions/p2"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIs(cm.exception.billed, False)
        self.assertEqual(s.delete.call_count, 2)

    def test_aborted_prediction_reports_not_billed(self):
        pred = {
            "id": "p2b",
            "status": "aborted",
            "error": "deadline",
            "output": None,
            "urls": {"get": "https://api.replicate.com/v1/predictions/p2b"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIs(cm.exception.billed, False)

    def test_canceled_prediction_billing_unknown(self):
        pred = {
            "id": "p2c",
            "status": "canceled",
            "output": None,
            "urls": {"get": "https://api.replicate.com/v1/predictions/p2c"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIsNone(cm.exception.billed)

    def test_422_is_not_retried(self):
        s = self._session(FakeResp(422, {"detail": "input.aspect_ratio: invalid"}), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIs(cm.exception.billed, False)
        creates = [c for c in s.post.call_args_list if c.args[0].endswith("/predictions")]
        self.assertEqual(len(creates), 1)

    def test_429_is_retried_then_succeeds(self):
        pred = {
            "id": "p429",
            "status": "succeeded",
            "output": ["https://replicate.delivery/xezq/abc/out.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p429"},
        }
        calls = {"n": 0}

        def create_resp():
            calls["n"] += 1
            if calls["n"] == 1:
                return FakeResp(429, {"detail": "throttled"}, headers={"Retry-After": "0"})
            return FakeResp(201, pred)

        s = self._session(create_resp, [], None)
        res = self._run_generate(s)
        self.assertEqual(res.meta["prediction_id"], "p429")
        creates = [c for c in s.post.call_args_list if c.args[0].endswith("/predictions")]
        self.assertEqual(len(creates), 2)

    def test_refuses_foreign_download_host(self):
        pred = {
            "id": "p3",
            "status": "succeeded",
            "output": ["https://evil.example.com/x.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p3"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIn("unexpected host", str(cm.exception))
        self.assertEqual(s.delete.call_count, 2)

    def test_refuses_http_download(self):
        pred = {
            "id": "p3h",
            "status": "succeeded",
            "output": ["http://replicate.delivery/x.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p3h"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIn("non-HTTPS", str(cm.exception))

    def test_refuses_replicate_com_apex(self):
        pred = {
            "id": "p3c",
            "status": "succeeded",
            "output": ["https://replicate.com/static/out.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p3c"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIn("unexpected host", str(cm.exception))

    def test_allows_replicate_delivery_subdomain(self):
        pred = {
            "id": "p-sub",
            "status": "succeeded",
            "output": ["https://pbxt.replicate.delivery/xezq/abc/out.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p-sub"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        res = self._run_generate(s)
        self.assertEqual(res.meta["prediction_id"], "p-sub")
        self.assertEqual(
            self.plain.get.call_args.args[0],
            "https://pbxt.replicate.delivery/xezq/abc/out.png",
        )

    def _generate_with_real_auth_session(self, pred, *, plain_status):
        """Keep _session() header setup; mock only the transport."""
        s = rp._session()
        self.assertEqual(s.headers.get("Authorization"), "Bearer r8_test_not_real")
        file_n = iter(range(100))

        def post(url, **kw):
            if url.endswith("/files"):
                n = next(file_n)
                return FakeResp(
                    201,
                    {"id": f"f{n}", "urls": {"get": f"https://api.replicate.com/v1/files/f{n}"}},
                )
            self.sent = kw["json"]
            self.sent_headers = kw["headers"]
            return FakeResp(201, pred)

        s.post = post
        s.delete = mock.MagicMock()
        png = FakeResp(200, content=_png_bytes((64, 64)))

        def auth_handler(url, _kw, _headers):
            if "replicate.delivery" in url:
                return png
            return FakeResp(200, pred)

        auth_gets = _record_gets(s, auth_handler)
        plain = rp._plain_session()
        self.assertIsNone(
            next(
                (v for k, v in dict(plain.headers).items() if k.lower() == "authorization"),
                None,
            )
        )
        plain_gets = _record_gets(plain, lambda _url, _kw, _headers: FakeResp(plain_status))
        with mock.patch.object(rp, "_session", return_value=s):
            with mock.patch.object(rp, "_plain_session", return_value=plain):
                res = rp.generate(self.req, rp.plan(self.req))
        return res, plain_gets, auth_gets

    def test_download_retries_with_token_on_401(self):
        pred = {
            "id": "p401",
            "status": "succeeded",
            "output": ["https://replicate.delivery/xezq/abc/out.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p401"},
        }
        res, plain_gets, auth_gets = self._generate_with_real_auth_session(
            pred, plain_status=401
        )
        self.assertEqual(res.meta["prediction_id"], "p401")
        self.assertEqual(len(plain_gets), 1)
        self.assertNotIn(
            "authorization", {k.lower() for k in plain_gets[0]["headers"]}
        )
        self.assertEqual(plain_gets[0]["allow_redirects"], False)
        delivery_auth = [g for g in auth_gets if "replicate.delivery" in g["url"]]
        self.assertEqual(len(delivery_auth), 1)
        self.assertEqual(
            delivery_auth[0]["headers"].get("Authorization"), "Bearer r8_test_not_real"
        )
        self.assertEqual(delivery_auth[0]["allow_redirects"], False)

    def test_download_retries_with_token_on_403(self):
        pred = {
            "id": "p403",
            "status": "succeeded",
            "output": ["https://replicate.delivery/xezq/abc/out.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p403"},
        }
        res, plain_gets, auth_gets = self._generate_with_real_auth_session(
            pred, plain_status=403
        )
        self.assertEqual(res.meta["prediction_id"], "p403")
        self.assertNotIn(
            "authorization", {k.lower() for k in plain_gets[0]["headers"]}
        )
        delivery_auth = [g for g in auth_gets if "replicate.delivery" in g["url"]]
        self.assertEqual(len(delivery_auth), 1)
        self.assertEqual(
            delivery_auth[0]["headers"].get("Authorization"), "Bearer r8_test_not_real"
        )

    def test_unauth_download_retries_429(self):
        pred = {
            "id": "p429dl",
            "status": "succeeded",
            "output": ["https://replicate.delivery/xezq/abc/out.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p429dl"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        png = _png_bytes((64, 64))
        plain = rp._plain_session()
        plain.get = mock.Mock(
            side_effect=[
                FakeResp(429, headers={"Retry-After": "0"}),
                FakeResp(200, content=png),
            ]
        )
        with mock.patch.object(rp, "_session", return_value=s):
            with mock.patch.object(rp, "_plain_session", return_value=plain):
                res = rp.generate(self.req, rp.plan(self.req))
        self.assertEqual(res.meta["prediction_id"], "p429dl")
        self.assertEqual(plain.get.call_count, 2)
        for call in plain.get.call_args_list:
            self.assertEqual(call.kwargs.get("allow_redirects"), False)
            self.assertNotIn("Authorization", dict(plain.headers))

    def test_poll_url_must_be_predictions_api(self):
        pred = {
            "id": "p-evil",
            "status": "starting",
            "output": None,
            "urls": {"get": "https://evil.example.com/steal"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIn("unexpected URL", str(cm.exception))
        self.assertIn("https://api.replicate.com/v1/predictions/", str(cm.exception))

    def test_poll_url_rejects_files_endpoint(self):
        pred = {
            "id": "p-files",
            "status": "starting",
            "output": None,
            "urls": {"get": "https://api.replicate.com/v1/files/f1"},
        }
        s = self._session(FakeResp(201, pred), [], None)
        with mock.patch.object(rp, "_session", return_value=s):
            with self.assertRaises(ProviderError) as cm:
                rp.generate(self.req, rp.plan(self.req))
        self.assertIn("unexpected URL", str(cm.exception))

    def test_resume_skips_create_and_upload(self):
        pred = {
            "id": "p-resume",
            "status": "succeeded",
            "output": ["https://replicate.delivery/xezq/abc/out.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p-resume"},
        }
        s = mock.MagicMock()
        s.get.return_value = FakeResp(200, pred)
        res = self._run_generate(s, resume_id="p-resume")
        self.assertEqual(res.meta["prediction_id"], "p-resume")
        s.post.assert_not_called()
        s.delete.assert_not_called()

    def test_timeout_resumes_listed_prediction(self):
        plan = rp.plan(self.req)
        pred = {
            "id": "p-found",
            "status": "succeeded",
            "model": plan.model,
            "input": {"prompt": plan.payload_preview["prompt"]},
            "output": ["https://replicate.delivery/xezq/abc/out.png"],
            "urls": {"get": "https://api.replicate.com/v1/predictions/p-found"},
        }
        s = mock.MagicMock()
        file_n = iter(range(100))

        def post(url, **kw):
            if url.endswith("/files"):
                n = next(file_n)
                return FakeResp(
                    201,
                    {"id": f"f{n}", "urls": {"get": f"https://api.replicate.com/v1/files/f{n}"}},
                )
            raise requests.Timeout("create timed out")

        def get(url, **kw):
            if url.rstrip("/").endswith("/predictions"):
                return FakeResp(200, {"results": [pred]})
            return FakeResp(200, pred)

        s.post.side_effect = post
        s.get.side_effect = get
        plain = rp._plain_session()
        plain.get = mock.Mock(return_value=FakeResp(200, content=_png_bytes((64, 64))))
        with mock.patch.object(rp, "_plain_session", return_value=plain):
            with mock.patch.object(rp, "_session", return_value=s):
                res = rp.generate(self.req, plan)
        self.assertEqual(res.meta["prediction_id"], "p-found")
        self.assertEqual(s.delete.call_count, 2)


class ReplicateOutputRedirectTests(unittest.TestCase):
    def setUp(self):
        os.environ["REPLICATE_API_TOKEN"] = "r8_test_not_real"
        self.sleep = mock.patch.object(rp.time, "sleep")
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def _auth(self):
        return rp._session()

    def test_refuses_redirect_to_foreign_host(self):
        plain = rp._plain_session()
        _record_gets(
            plain,
            lambda _url, _kw, _headers: FakeResp(
                302, headers={"Location": "https://evil.example.com/x.png"}
            ),
        )
        with mock.patch.object(rp, "_plain_session", return_value=plain):
            with self.assertRaises(ProviderError) as cm:
                rp._download(self._auth(), "https://replicate.delivery/x.png")
        self.assertIn("unexpected host", str(cm.exception))
        self.assertIn("evil.example.com", str(cm.exception))

    def test_refuses_http_redirect(self):
        plain = rp._plain_session()
        _record_gets(
            plain,
            lambda _url, _kw, _headers: FakeResp(
                302, headers={"Location": "http://replicate.delivery/x.png"}
            ),
        )
        with mock.patch.object(rp, "_plain_session", return_value=plain):
            with self.assertRaises(ProviderError) as cm:
                rp._download(self._auth(), "https://replicate.delivery/x.png")
        self.assertIn("non-HTTPS", str(cm.exception))

    def test_follows_relative_redirect_on_same_host(self):
        png = b"img-bytes"
        plain = rp._plain_session()

        def handler(url, _kw, _headers):
            if url.endswith("/x.png"):
                return FakeResp(302, headers={"Location": "/y.png"})
            return FakeResp(200, content=png)

        gets = _record_gets(plain, handler)
        with mock.patch.object(rp, "_plain_session", return_value=plain):
            data = rp._download(self._auth(), "https://replicate.delivery/x.png")
        self.assertEqual(data, png)
        self.assertEqual(gets[1]["url"], "https://replicate.delivery/y.png")
        self.assertTrue(all(g["allow_redirects"] is False for g in gets))

    def test_too_many_redirects(self):
        plain = rp._plain_session()
        _record_gets(
            plain,
            lambda _url, _kw, _headers: FakeResp(
                302, headers={"Location": "https://replicate.delivery/next.png"}
            ),
        )
        with mock.patch.object(rp, "_plain_session", return_value=plain):
            with self.assertRaises(ProviderError) as cm:
                rp._download(self._auth(), "https://replicate.delivery/start.png")
        self.assertIn("too many redirects", str(cm.exception))

    def test_empty_location(self):
        plain = rp._plain_session()
        _record_gets(plain, lambda _url, _kw, _headers: FakeResp(302, headers={}))
        with mock.patch.object(rp, "_plain_session", return_value=plain):
            with self.assertRaises(ProviderError) as cm:
                rp._download(self._auth(), "https://replicate.delivery/x.png")
        self.assertIn("empty Location", str(cm.exception))

    def test_auth_retry_keeps_token_on_same_host_redirect(self):
        auth = self._auth()

        def auth_handler(url, _kw, _headers):
            if url.endswith("/x.png"):
                return FakeResp(
                    302, headers={"Location": "https://replicate.delivery/y.png"}
                )
            return FakeResp(200, content=b"img")

        auth_gets = _record_gets(auth, auth_handler)
        plain = rp._plain_session()
        plain_gets = _record_gets(plain, lambda _url, _kw, _headers: FakeResp(401))
        with mock.patch.object(rp, "_plain_session", return_value=plain):
            data = rp._download(auth, "https://replicate.delivery/x.png")
        self.assertEqual(data, b"img")
        self.assertEqual(len(plain_gets), 1)
        self.assertNotIn(
            "authorization", {k.lower() for k in plain_gets[0]["headers"]}
        )
        self.assertEqual(len(auth_gets), 2)
        for g in auth_gets:
            self.assertEqual(
                g["headers"].get("Authorization"), "Bearer r8_test_not_real"
            )
            self.assertEqual(g["allow_redirects"], False)

    def test_auth_retry_drops_token_when_host_changes(self):
        auth = self._auth()
        auth_gets = _record_gets(
            auth,
            lambda url, _kw, _headers: FakeResp(
                302, headers={"Location": "https://api.replicate.com/v1/files/f1"}
            )
            if "replicate.delivery" in url
            else FakeResp(200, content=b"should-not-use-auth"),
        )
        plains = []

        def new_plain():
            sess = requests.Session()

            def handler(url, _kw, _headers):
                if "replicate.delivery" in url:
                    return FakeResp(401)
                return FakeResp(200, content=b"img")

            plains.append(_record_gets(sess, handler))
            return sess

        with mock.patch.object(rp, "_plain_session", side_effect=new_plain):
            data = rp._download(auth, "https://replicate.delivery/x.png")
        self.assertEqual(data, b"img")
        self.assertEqual(len(plains[0]), 1)
        self.assertIn("replicate.delivery", plains[0][0]["url"])
        self.assertNotIn(
            "authorization", {k.lower() for k in plains[0][0]["headers"]}
        )
        self.assertEqual(len(plains[1]), 1)
        self.assertIn("api.replicate.com", plains[1][0]["url"])
        self.assertNotIn(
            "authorization", {k.lower() for k in plains[1][0]["headers"]}
        )
        self.assertEqual(plains[1][0]["allow_redirects"], False)
        auth_delivery = [g for g in auth_gets if "replicate.delivery" in g["url"]]
        self.assertEqual(len(auth_delivery), 1)
        self.assertEqual(
            auth_delivery[0]["headers"].get("Authorization"), "Bearer r8_test_not_real"
        )
        self.assertEqual(
            [g for g in auth_gets if "api.replicate.com" in g["url"]], []
        )


class ResolveTests(unittest.TestCase):
    def test_only_replicate_key_uses_replicate(self):
        with mock.patch.dict(
            os.environ, {"IMAGE_PROVIDER": "", "FAL_KEY": "", "REPLICATE_API_TOKEN": "x"}
        ):
            name, why = resolve_provider(None, {})
            self.assertEqual(name, "replicate")
            self.assertEqual(why, "only REPLICATE_API_TOKEN is set")

    def test_only_fal_key_uses_fal(self):
        with mock.patch.dict(
            os.environ, {"IMAGE_PROVIDER": "", "FAL_KEY": "a", "REPLICATE_API_TOKEN": ""}
        ):
            name, why = resolve_provider(None, {})
            self.assertEqual(name, "fal")
            self.assertEqual(why, "only FAL_KEY is set")

    def test_both_keys_default_to_replicate(self):
        with mock.patch.dict(
            os.environ, {"IMAGE_PROVIDER": "", "FAL_KEY": "a", "REPLICATE_API_TOKEN": "b"}
        ):
            self.assertEqual(resolve_provider(None, {})[0], "replicate")

    def test_neither_key_defaults_to_replicate(self):
        with mock.patch.dict(
            os.environ, {"IMAGE_PROVIDER": "", "FAL_KEY": "", "REPLICATE_API_TOKEN": ""}
        ):
            name, why = resolve_provider(None, {})
            self.assertEqual(name, "replicate")
            self.assertEqual(why, "no key set")

    def test_cli_provider_overrides_spec_and_keys(self):
        with mock.patch.dict(
            os.environ, {"IMAGE_PROVIDER": "", "FAL_KEY": "", "REPLICATE_API_TOKEN": "x"}
        ):
            self.assertEqual(resolve_provider("fal", {"provider": "replicate"})[0], "fal")

    def test_spec_provider_overrides_env_and_keys(self):
        with mock.patch.dict(
            os.environ, {"IMAGE_PROVIDER": "replicate", "FAL_KEY": "a", "REPLICATE_API_TOKEN": "b"}
        ):
            self.assertEqual(resolve_provider(None, {"provider": "fal"})[0], "fal")

    def test_image_provider_env_overrides_keys(self):
        with mock.patch.dict(
            os.environ, {"IMAGE_PROVIDER": "fal", "FAL_KEY": "a", "REPLICATE_API_TOKEN": "b"}
        ):
            self.assertEqual(resolve_provider(None, {})[0], "fal")
        with mock.patch.dict(
            os.environ, {"IMAGE_PROVIDER": "replicate", "FAL_KEY": "a", "REPLICATE_API_TOKEN": "b"}
        ):
            self.assertEqual(resolve_provider(None, {})[0], "replicate")


class EnvLoadTests(unittest.TestCase):
    def test_project_root_only_and_allowlist(self):
        gba = _load_script()
        tmp = Path(tempfile.mkdtemp())
        (tmp / ".claude").mkdir()
        (tmp / ".env").write_text("REPLICATE_API_TOKEN=from-project\nEVIL=should-not-load\n")
        nested = tmp / "nested"
        nested.mkdir()
        (nested / ".env").write_text("REPLICATE_API_TOKEN=from-nested\nFAL_KEY=from-nested\n")
        env = {k: v for k, v in os.environ.items()}
        env.pop("REPLICATE_API_TOKEN", None)
        env.pop("FAL_KEY", None)
        env.pop("EVIL", None)
        env.pop("IMAGE_PROVIDER", None)
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(gba, "_project_root", return_value=tmp):
                gba._load_env()
                self.assertEqual(os.environ.get("REPLICATE_API_TOKEN"), "from-project")
                self.assertNotIn("EVIL", os.environ)
                self.assertIsNone(os.environ.get("FAL_KEY"))

    def test_does_not_override_existing_env(self):
        gba = _load_script()
        tmp = Path(tempfile.mkdtemp())
        (tmp / ".env").write_text("REPLICATE_API_TOKEN=from-file\n")
        with mock.patch.dict(os.environ, {"REPLICATE_API_TOKEN": "already-set"}):
            with mock.patch.object(gba, "_project_root", return_value=tmp):
                gba._load_env()
                self.assertEqual(os.environ["REPLICATE_API_TOKEN"], "already-set")

    def test_project_root_prefers_claude_project_dir(self):
        gba = _load_script()
        project = Path(tempfile.mkdtemp()).resolve()
        cwd = Path(tempfile.mkdtemp()).resolve()
        (cwd / ".claude").mkdir()
        old = os.getcwd()
        try:
            os.chdir(cwd)
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(project)}):
                self.assertEqual(gba._project_root().resolve(), project)
        finally:
            os.chdir(old)

    def test_project_root_uses_cwd_when_it_has_env(self):
        gba = _load_script()
        parent = Path(tempfile.mkdtemp()).resolve()
        (parent / ".claude").mkdir()
        cwd = parent / "nested"
        cwd.mkdir()
        (cwd / ".env").write_text("REPLICATE_API_TOKEN=from-cwd\n")
        old = os.getcwd()
        try:
            os.chdir(cwd)
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(gba._project_root().resolve(), cwd)
        finally:
            os.chdir(old)

    def test_project_root_walks_to_parent_with_claude(self):
        gba = _load_script()
        parent = Path(tempfile.mkdtemp()).resolve()
        (parent / ".claude").mkdir()
        cwd = parent / "nested" / "deeper"
        cwd.mkdir(parents=True)
        old = os.getcwd()
        try:
            os.chdir(cwd)
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(gba._project_root().resolve(), parent)
        finally:
            os.chdir(old)

    def test_project_root_skips_home_even_when_home_has_claude(self):
        gba = _load_script()
        home = Path(tempfile.mkdtemp()).resolve()
        (home / ".claude" / "skills" / "meta-ads-static-creator").mkdir(parents=True)
        (home / ".env").write_text("REPLICATE_API_TOKEN=from-home\nFAL_KEY=from-home\n")
        nested = home / "Downloads"
        nested.mkdir()
        old = os.getcwd()
        try:
            os.chdir(nested)
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("CLAUDE_PROJECT_DIR", "REPLICATE_API_TOKEN", "FAL_KEY")
            }
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch.object(
                    gba, "_is_home", side_effect=lambda p: Path(p).resolve() == home
                ):
                    self.assertNotEqual(gba._project_root().resolve(), home)
                    gba._load_env()
                    self.assertIsNone(os.environ.get("REPLICATE_API_TOKEN"))
                    self.assertIsNone(os.environ.get("FAL_KEY"))
        finally:
            os.chdir(old)

    def test_load_env_refuses_home_root(self):
        gba = _load_script()
        home = Path(tempfile.mkdtemp()).resolve()
        (home / ".env").write_text("REPLICATE_API_TOKEN=from-home\n")
        env = {k: v for k, v in os.environ.items()}
        env.pop("REPLICATE_API_TOKEN", None)
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(gba, "_project_root", return_value=home):
                with mock.patch.object(gba, "_is_home", return_value=True):
                    gba._load_env()
                    self.assertIsNone(os.environ.get("REPLICATE_API_TOKEN"))

    def test_is_home_catches_runtime_error_from_path_home(self):
        gba = _load_script()
        with mock.patch.object(
            gba.Path, "home", side_effect=RuntimeError("no home directory")
        ):
            self.assertFalse(gba._is_home(Path("/tmp")))


class FalDownloadTests(unittest.TestCase):
    def test_https_fal_media_ok(self):
        with mock.patch.object(
            fp.requests, "get", return_value=FakeResp(200, content=b"img")
        ) as get:
            data = fp._download_output("https://v3b.fal.media/files/b/x/out.png")
        self.assertEqual(data, b"img")
        self.assertEqual(get.call_args.kwargs.get("timeout"), 120)
        self.assertEqual(get.call_args.kwargs.get("allow_redirects"), False)
        self.assertNotIn("headers", get.call_args.kwargs)

    def test_https_v3_fal_media_ok(self):
        with mock.patch.object(fp.requests, "get", return_value=FakeResp(200, content=b"img")):
            fp._download_output("https://v3.fal.media/files/x.png")

    def test_https_fal_run_subdomain_ok(self):
        with mock.patch.object(fp.requests, "get", return_value=FakeResp(200, content=b"img")):
            fp._download_output("https://queue.fal.run/out.png")

    def test_refuses_foreign_host(self):
        with self.assertRaises(ProviderError) as cm:
            fp._download_output("https://evil.example.com/x.png")
        self.assertIn("unexpected host", str(cm.exception))

    def test_refuses_http(self):
        with self.assertRaises(ProviderError) as cm:
            fp._download_output("http://fal.media/x.png")
        self.assertIn("non-HTTPS", str(cm.exception))

    def test_follows_https_redirect_on_allowlisted_host(self):
        hops = [
            FakeResp(302, headers={"Location": "https://v3.fal.media/files/out.png"}),
            FakeResp(200, content=b"img"),
        ]
        with mock.patch.object(fp.requests, "get", side_effect=hops) as get:
            data = fp._download_output("https://v3b.fal.media/files/b/x/out.png")
        self.assertEqual(data, b"img")
        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args_list[1].args[0], "https://v3.fal.media/files/out.png"
        )
        for call in get.call_args_list:
            self.assertEqual(call.kwargs.get("allow_redirects"), False)

    def test_follows_relative_redirect(self):
        hops = [
            FakeResp(302, headers={"Location": "/files/out.png"}),
            FakeResp(200, content=b"img"),
        ]
        with mock.patch.object(fp.requests, "get", side_effect=hops) as get:
            data = fp._download_output("https://v3b.fal.media/files/b/x/out.png")
        self.assertEqual(data, b"img")
        self.assertEqual(get.call_args_list[1].args[0], "https://v3b.fal.media/files/out.png")

    def test_refuses_redirect_to_foreign_host(self):
        with mock.patch.object(
            fp.requests,
            "get",
            return_value=FakeResp(
                302, headers={"Location": "https://evil.example.com/x.png"}
            ),
        ):
            with self.assertRaises(ProviderError) as cm:
                fp._download_output("https://v3b.fal.media/files/b/x/out.png")
        self.assertIn("unexpected host", str(cm.exception))

    def test_refuses_http_redirect(self):
        with mock.patch.object(
            fp.requests,
            "get",
            return_value=FakeResp(
                302, headers={"Location": "http://fal.media/x.png"}
            ),
        ):
            with self.assertRaises(ProviderError) as cm:
                fp._download_output("https://v3b.fal.media/files/b/x/out.png")
        self.assertIn("non-HTTPS", str(cm.exception))

    def test_too_many_redirects(self):
        with mock.patch.object(
            fp.requests,
            "get",
            return_value=FakeResp(
                302, headers={"Location": "https://v3.fal.media/next.png"}
            ),
        ):
            with self.assertRaises(ProviderError) as cm:
                fp._download_output("https://v3b.fal.media/start.png")
        self.assertIn("too many redirects", str(cm.exception))

    def test_empty_location(self):
        with mock.patch.object(
            fp.requests, "get", return_value=FakeResp(302, headers={})
        ):
            with self.assertRaises(ProviderError) as cm:
                fp._download_output("https://v3b.fal.media/files/b/x/out.png")
        self.assertIn("empty Location", str(cm.exception))


class CliEstimateTests(unittest.TestCase):
    """--estimate must never touch the network: run with no keys and a broken proxy."""

    def _spec(self, tmp, extra=None):
        imgs = [_png(tmp / "ref.png"), _png(tmp / "pack.png"), _png(tmp / "hand.png")]
        spec = {
            "output_name": "demo",
            "plate_prompt": "A plate.",
            "reference_image": str(imgs[0]),
            "product_images": [str(imgs[1])],
            "product_scale_reference": str(imgs[2]),
            "variants": {
                "feed_4x5": {"aspect_ratio": "4:5"},
                "fullscreen_9x16": {"aspect_ratio": "9:16"},
            },
        }
        if extra:
            spec.update(extra)
        (tmp / "spec.json").write_text(json.dumps(spec))
        return tmp

    def _run(self, tmp, args, extra_env=None):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("FAL_KEY", "REPLICATE_API_TOKEN", "IMAGE_PROVIDER")
        }
        env.update(HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9")
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp,
        )

    def test_estimate_both_providers_default_low(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        for provider in ("fal", "replicate"):
            out = self._run(tmp, ["--variant", "feed_4x5", "--provider", provider, "--estimate"])
            self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
            self.assertIn('"provider": "%s"' % provider, out.stdout)
            self.assertIn('"quality": "low"', out.stdout)
        self.assertIn('"est_cost_usd": 0.012', out.stdout)
        self.assertEqual(list(tmp.glob("*-plate_v*.png")), [])

    def test_estimate_final_is_high(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        out = self._run(
            tmp, ["--variant", "feed_4x5", "--provider", "replicate", "--final", "--estimate"]
        )
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn('"quality": "high"', out.stdout)
        self.assertIn('"est_cost_usd": 0.128', out.stdout)

    def test_estimate_quality_medium(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        out = self._run(
            tmp,
            ["--variant", "feed_4x5", "--provider", "replicate", "--quality", "medium", "--estimate"],
        )
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn('"quality": "medium"', out.stdout)
        self.assertIn('"est_cost_usd": 0.047', out.stdout)

    def test_estimate_spec_quality(self):
        tmp = self._spec(Path(tempfile.mkdtemp()), extra={"quality": "high"})
        out = self._run(tmp, ["--variant", "feed_4x5", "--provider", "replicate", "--estimate"])
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn('"quality": "high"', out.stdout)
        self.assertIn('"est_cost_usd": 0.128', out.stdout)

    def test_estimate_quality_overrides_final(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        out = self._run(
            tmp,
            [
                "--variant",
                "feed_4x5",
                "--provider",
                "replicate",
                "--final",
                "--quality",
                "medium",
                "--estimate",
            ],
        )
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn('"quality": "medium"', out.stdout)
        self.assertIn('"est_cost_usd": 0.047', out.stdout)


    def test_estimate_neither_key_defaults_to_replicate(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        out = self._run(tmp, ["--variant", "feed_4x5", "--estimate"])
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn('"provider": "replicate"', out.stdout)
        self.assertIn("no key set", out.stdout)

    def test_estimate_both_keys_defaults_to_replicate(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        out = self._run(
            tmp,
            ["--variant", "feed_4x5", "--estimate"],
            extra_env={"FAL_KEY": "fal-test", "REPLICATE_API_TOKEN": "r8_test"},
        )
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn('"provider": "replicate"', out.stdout)

    def test_estimate_only_fal_key_uses_fal(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        out = self._run(
            tmp,
            ["--variant", "feed_4x5", "--estimate"],
            extra_env={"FAL_KEY": "fal-test"},
        )
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn('"provider": "fal"', out.stdout)

    def test_estimate_cli_override_wins_over_both_keys(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        out = self._run(
            tmp,
            ["--variant", "feed_4x5", "--provider", "fal", "--estimate"],
            extra_env={"FAL_KEY": "fal-test", "REPLICATE_API_TOKEN": "r8_test"},
        )
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn('"provider": "fal"', out.stdout)

    def test_generate_neither_key_helpful_error(self):
        tmp = self._spec(Path(tempfile.mkdtemp()))
        out = self._run(tmp, ["--variant", "feed_4x5"])
        self.assertNotEqual(out.returncode, 0)
        msg = out.stderr + out.stdout
        self.assertIn("REPLICATE_API_TOKEN (recommended)", msg)
        self.assertIn("FAL_KEY", msg)
        self.assertEqual(list(tmp.glob("*-plate_v*.png")), [])


if __name__ == "__main__":
    unittest.main()
