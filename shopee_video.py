"""Extrator restrito a Shopee Vídeo público, sem cookies ou login.

A página de compartilhamento Shopee expõe o MP4 (com a marca d'água de origem)
no JSON __NEXT_DATA__. Apenas hosts Shopee e CDN oficiais são acessados.
"""
from __future__ import annotations

import json
import re
import socket
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_PAGE = 2 * 1024 * 1024
MAX_VIDEO = 250 * 1024 * 1024
TIME_LIMIT = 90
PAGE_HOSTS = {"br.shp.ee", "shp.ee", "x.shp.ee", "sv.shopee.com.br"}
SHORT_CODE = re.compile(r"^[A-Za-z0-9_-]{4,80}$")
VIDEO_CODE = re.compile(r"^[A-Za-z0-9_-]{8,120}={0,2}$")
NEXT_DATA = re.compile(
    r'<script\b(?=[^>]*\bid=["\']__NEXT_DATA__["\'])[^>]*>(.*?)</script>',
    flags=re.I | re.S,
)
USER_AGENT = ("Mozilla/5.0 (Linux; Android 14; Mobile) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36")


class ShopeeVideoError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


def _is_https_url(url: str, allowed_host) -> bool:
    try:
        p = urlparse(url)
        return (p.scheme == "https" and bool(p.hostname) and
                not p.username and not p.password and p.port is None and
                allowed_host(p.hostname.lower()))
    except ValueError:
        return False


def _page_host(host: str) -> bool:
    return host in PAGE_HOSTS


def _cdn_host(host: str) -> bool:
    # Reject lookalikes such as attacker-susercontent.com.
    return host.endswith(".susercontent.com")


class SafeRedirect(HTTPRedirectHandler):
    def __init__(self, allowed_host):
        super().__init__()
        self.allowed_host = allowed_host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_https_url(newurl, self.allowed_host):
            raise ShopeeVideoError(422, "O link foi redirecionado para fora da Shopee.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def normalize_shopee_link(url: str) -> tuple[str, str]:
    if not _is_https_url(url, _page_host):
        raise ShopeeVideoError(400, "Cole um link HTTPS do Shopee Vídeo.")
    p = urlparse(url)
    host = p.hostname.lower()
    parts = [segment for segment in p.path.split("/") if segment]
    if host == "sv.shopee.com.br":
        if len(parts) != 2 or parts[0] != "share-video" or not VIDEO_CODE.fullmatch(parts[1]):
            raise ShopeeVideoError(400, "Este endereço não é um vídeo compartilhado da Shopee.")
        return f"https://sv.shopee.com.br/share-video/{parts[1]}", parts[1]
    if len(parts) != 1 or not SHORT_CODE.fullmatch(parts[0]):
        raise ShopeeVideoError(400, "Link curto de Shopee Vídeo inválido.")
    return f"https://{host}/{parts[0]}", parts[0]


def fetch_video_url(shopee_link: str) -> str:
    page_url, _ = normalize_shopee_link(shopee_link)
    opener = build_opener(SafeRedirect(_page_host))
    request = Request(page_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    try:
        with opener.open(request, timeout=16) as response:
            final_url = response.geturl()
            final = urlparse(final_url)
            if not _is_https_url(final_url, _page_host) or final.hostname != "sv.shopee.com.br" or not final.path.startswith("/share-video/"):
                raise ShopeeVideoError(422, "O link não abriu um Shopee Vídeo público.")
            page = response.read(MAX_PAGE + 1)
            if len(page) > MAX_PAGE:
                raise ShopeeVideoError(422, "A página Shopee excedeu o limite de leitura.")
    except ShopeeVideoError:
        raise
    except (HTTPError, URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise ShopeeVideoError(422, "Não foi possível abrir o Shopee Vídeo público.") from exc

    match = NEXT_DATA.search(page.decode("utf-8", errors="replace"))
    if not match:
        raise ShopeeVideoError(422, "A Shopee não disponibilizou os dados públicos deste vídeo.")
    try:
        data = json.loads(match.group(1))
        video = data["props"]["pageProps"]["mediaInfo"]["video"]
        # Conteúdo que a própria página pública disponibiliza, com marca d'água.
        media_url = video.get("watermarkVideoUrl") or video.get("videoUrl")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ShopeeVideoError(422, "Não foi possível identificar o MP4 neste Shopee Vídeo.") from exc
    if not isinstance(media_url, str) or not _is_https_url(media_url, _cdn_host):
        raise ShopeeVideoError(422, "O vídeo não possui arquivo MP4 público em CDN autorizada.")
    if not urlparse(media_url).path.lower().endswith(".mp4"):
        raise ShopeeVideoError(422, "A página não forneceu um arquivo MP4 válido.")
    return media_url


def download_shopee(link: str, output: Path) -> Path:
    media_url = fetch_video_url(link)
    request = Request(media_url, headers={
        "User-Agent": USER_AGENT,
        "Referer": "https://sv.shopee.com.br/",
        "Accept": "video/mp4,*/*;q=0.8",
    })
    opener = build_opener(SafeRedirect(_cdn_host))
    start = time.monotonic()
    try:
        with opener.open(request, timeout=20) as response:
            mime = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if mime not in {"video/mp4", "application/octet-stream", "binary/octet-stream"}:
                raise ShopeeVideoError(422, "A Shopee não retornou um arquivo MP4.")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_VIDEO:
                raise ShopeeVideoError(413, "Este vídeo supera o limite de 250 MB.")
            count = 0
            with output.open("wb") as f:
                while True:
                    if time.monotonic() - start > TIME_LIMIT:
                        raise ShopeeVideoError(504, "A transferência da Shopee demorou demais.")
                    block = response.read(512 * 1024)
                    if not block:
                        break
                    count += len(block)
                    if count > MAX_VIDEO:
                        raise ShopeeVideoError(413, "Este vídeo supera o limite de 250 MB.")
                    f.write(block)
        with output.open("rb") as f:
            magic = f.read(12)
        if count < 12 or magic[4:8] != b"ftyp":
            raise ShopeeVideoError(422, "O arquivo retornado pela Shopee não é um MP4 válido.")
        return output
    except ShopeeVideoError:
        raise
    except (HTTPError, URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
        raise ShopeeVideoError(422, "Não foi possível baixar o MP4 público da Shopee.") from exc
