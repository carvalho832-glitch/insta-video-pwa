"""Offline smoke/security tests for Shopee Video links."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import shopee_video as s

SHORT = "https://br.shp.ee/pokbh020?fromSource=copy_link&smtt=0.0.9"
VIDEO = "https://sv.shopee.com.br/share-video/X2DWmtEkCgCTVVUTAAAAAA=="
CDN = "https://down-bs-br.vod.susercontent.com/api/v4/example.mp4"


class FakeResponse:
    def __init__(self, data, url, mime):
        self.buf = io.BytesIO(data)
        self.url = url
        self.headers = {"Content-Type": mime, "Content-Length": str(len(data))}

    def read(self, length=-1):
        return self.buf.read(length)

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ShopeeTests(unittest.TestCase):
    def test_short_and_long_links(self):
        self.assertEqual(s.normalize_shopee_link(SHORT)[0], "https://br.shp.ee/pokbh020")
        self.assertEqual(s.normalize_shopee_link(VIDEO)[0], VIDEO)

    def test_rejects_unsafe_links(self):
        for url in (
            "http://br.shp.ee/pokbh020",
            "https://br.shp.ee.evil.example/pokbh020",
            "https://br.shp.ee:8443/pokbh020",
            "https://br.shp.ee@evil.example/pokbh020",
            "https://sv.shopee.com.br/product/12345",
            "https://127.0.0.1/share-video/12345",
        ):
            with self.subTest(url=url):
                with self.assertRaises(s.ShopeeVideoError):
                    s.normalize_shopee_link(url)

    def test_rejects_wrong_cdn(self):
        self.assertFalse(s._is_https_url("https://evil-susercontent.com/video.mp4", s._cdn_host))
        self.assertFalse(s._is_https_url("https://localhost/video.mp4", s._cdn_host))
        self.assertTrue(s._is_https_url(CDN, s._cdn_host))

    def test_extracts_public_mp4(self):
        payload = {"props": {"pageProps": {"mediaInfo": {"video": {"watermarkVideoUrl": CDN}}}}}
        html = ('<html><script id="__NEXT_DATA__" type="application/json">' +
                json.dumps(payload) + '</script></html>').encode()
        response = FakeResponse(html, VIDEO, "text/html")
        with patch.object(s, "build_opener") as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(s.fetch_video_url(SHORT), CDN)

    def test_missing_mp4_fails(self):
        html = b'<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"mediaInfo":{"video":{}}}}}</script></html>'
        with patch.object(s, "build_opener") as opener:
            opener.return_value.open.return_value = FakeResponse(html, VIDEO, "text/html")
            with self.assertRaises(s.ShopeeVideoError):
                s.fetch_video_url(SHORT)

    def test_stream_valid_mp4(self):
        data = b"\\x00\\x00\\x00\\x18ftypisom" + b"0" * 1024
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.mp4"
            with patch.object(s, "fetch_video_url", return_value=CDN):
                with patch.object(s, "build_opener") as opener:
                    opener.return_value.open.return_value = FakeResponse(data, CDN, "video/mp4")
                    s.download_shopee(SHORT, path)
            self.assertEqual(path.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
