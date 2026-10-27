"""TikSalva - PWA para salvar videos publicos do TikTok autorizados pelo autor."""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MAX_MB = 120
MAX_BYTES = MAX_MB * 1024 * 1024
PROCESS_TIMEOUT = 105
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.I)
LONG_URL = re.compile(r"^/@[A-Za-z0-9._-]{1,50}/video/(\d{10,24})/?$")
OTHER_VIDEO = re.compile(r"^/(?:video|v)/(\d{10,24})/?$")
SHORT_URL = re.compile(r"^/[A-Za-z0-9_-]{5,100}/?$")
T_URL = re.compile(r"^/t/[A-Za-z0-9_-]{5,100}/?$")
DOMAINS = {"www.tiktok.com", "tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}

app = FastAPI(title="TikSalva", docs_url=None, redoc_url=None)
logger = logging.getLogger("tiksalva")
queue_lock = threading.Lock()
current = threading.BoundedSemaphore(2)
accesses = defaultdict(deque)


class DownloadRequest(BaseModel):
    url: str = Field(min_length=10, max_length=1800)
    allow_external_fallback: bool = True


def normalize_link(text: str) -> tuple[str, str]:
    match = URL_IN_TEXT.search(text.strip())
    if not match:
        raise ValueError("Cole o link de um video publico do TikTok.")
    raw = match.group(0).rstrip(".,;!)]}")
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Este link nao e valido.") from exc

    if (
        parsed.scheme != "https"
        or host not in DOMAINS
        or parsed.username
        or parsed.password
        or port is not None
    ):
        raise ValueError("Aceitamos apenas links HTTPS oficiais do TikTok.")

    path = parsed.path
    long_match = LONG_URL.fullmatch(path)
    short_host = host in {"vm.tiktok.com", "vt.tiktok.com"}
    if short_host:
        if not SHORT_URL.fullmatch(path):
            raise ValueError("O link curto do TikTok nao parece valido.")
    elif not (long_match or OTHER_VIDEO.fullmatch(path) or T_URL.fullmatch(path)):
        raise ValueError("Cole o link de um video, nao de perfil, foto ou transmissao.")

    video_id = (
        (long_match or OTHER_VIDEO.fullmatch(path)).group(1)
        if (long_match or OTHER_VIDEO.fullmatch(path))
        else hashlib.sha256((host + path).encode()).hexdigest()[:12]
    )
    return urlunsplit(("https", host, path, "", "")), video_id


def permitted(ip: str) -> bool:
    now = time.monotonic()
    with queue_lock:
        events = accesses[ip]
        while events and now - events[0] > 15 * 60:
            events.popleft()
        if len(events) >= 10:
            return False
        events.append(now)
        if len(accesses) > 2000:
            for key, old in list(accesses.items())[:500]:
                if not old or now - old[-1] > 900:
                    accesses.pop(key, None)
        return True



def classify_error(error: str) -> tuple[int, str]:
    lower = error.lower()
    if any(v in lower for v in ["larger than", "max-filesize", "file is larger"]):
        return 413, "O video ultrapassa 120 MB."
    if any(v in lower for v in ["private", "login required", "age-restricted", "not available"]):
        return 422, "Video indisponivel, privado ou protegido por login."
    if "unsupported url" in lower:
        return 422, "Este endereco nao aponta para um video compativel."
    if any(v in lower for v in ["403", "429", "blocked", "extract webpage", "universal data"]):
        return 422, "O TikTok bloqueou a extracao automatica para este video."
    return 422, "Nao conseguimos extrair o MP4 desse link."


# Somente domínios de media/publicação conhecidos. Nunca seguir URLs arbitrárias
# retornadas por um terceiro, para não permitir SSRF contra a infraestrutura.
MEDIA_HOST_SUFFIXES = (
    "tikwm.com", "tikcdn.com", "tiktokcdn.com",
    "tiktokv.com", "byteoversea.com", "byteimg.com",
    "ibyteimg.com", "muscdn.com", "tiktok.com",
)


def approved_media_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
        hostname = (parts.hostname or "").lower().rstrip(".")
        return (
            parts.scheme == "https"
            and parts.username is None and parts.password is None
            and parts.port is None
            and any(hostname == suffix or hostname.endswith("." + suffix)
                    for suffix in MEDIA_HOST_SUFFIXES)
        )
    except ValueError:
        return False


def alternative_download(url: str, target: Path) -> bool:
    """Fallback externo opcional: repassa apenas link publico ao TikWM."""
    with requests.Session() as session:
        try:
            r = session.post(
                "https://www.tikwm.com/api/",
                data={"url": url, "hd": "1"},
                timeout=(7, 18),
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            r.raise_for_status()
            info = r.json()
            if info.get("code") != 0 or not isinstance(info.get("data"), dict):
                logger.info("Alternative service did not return a public video")
                return False
            video = info["data"]
            # O serviço fornece variantes sem marca d'água, quando disponíveis.
            media = video.get("hdplay") or video.get("play")
            if not isinstance(media, str) or not media:
                return False
            media = urljoin("https://www.tikwm.com", media)
            for _ in range(4):
                if not approved_media_url(media):
                    logger.warning("Alternative provided unsupported media host")
                    return False
                with session.get(
                    media, stream=True, timeout=(7, 24), allow_redirects=False,
                    headers={"Referer": "https://www.tikwm.com/", "User-Agent": "Mozilla/5.0"}
                ) as stream:
                    if stream.status_code in {301, 302, 303, 307, 308}:
                        location = stream.headers.get("Location")
                        if not location:
                            return False
                        media = urljoin(media, location)
                        continue
                    stream.raise_for_status()
                    ctype = stream.headers.get("Content-Type", "").lower()
                    if not (ctype.startswith("video/") or "octet-stream" in ctype):
                        logger.info("Alternative did not return a video content-type")
                        return False
                    size_header = stream.headers.get("Content-Length")
                    if size_header and int(size_header) > MAX_BYTES:
                        raise HTTPException(status_code=413, detail="O video ultrapassa 120 MB.")
                    total = 0
                    with target.open("wb") as out:
                        for chunk in stream.iter_content(chunk_size=1024 * 256):
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > MAX_BYTES:
                                raise HTTPException(status_code=413, detail="O video ultrapassa 120 MB.")
                            out.write(chunk)
                    if total < 1000:
                        target.unlink(missing_ok=True)
                        return False
                    return True
        except HTTPException:
            raise
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            logger.warning("Alternative download failed: %s", type(exc).__name__)
    return False


@app.get("/api/health")
def health():
    return {"ok": True, "app": "TikSalva", "max_mb": MAX_MB, "version": "1.1"}


@app.post("/api/download")
def download(payload: DownloadRequest, request: Request):
    try:
        clean_url, video_id = normalize_link(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ip = request.client.host if request.client else "unknown"
    if not permitted(ip):
        raise HTTPException(status_code=429, detail="Limite temporario atingido. Tente novamente em 15 minutos.")
    if not current.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Ja temos dois downloads em andamento. Tente novamente.")

    temp = Path(tempfile.mkdtemp(prefix="tiksalva-"))
    completed = False
    try:
        common = [
            sys.executable, "-m", "yt_dlp",
            "--no-playlist", "--no-progress", "--no-warnings",
            "--no-part", "--no-mtime", "--no-cache-dir",
            "--no-write-subs", "--no-write-auto-subs",
            "--no-write-thumbnail", "--no-write-info-json",
            "--no-write-description",
            "--max-filesize", f"{MAX_MB}M",
            "--socket-timeout", "12", "--retries", "1",
            "--fragment-retries", "1", "--extractor-retries", "1",
            "--format", "best[ext=mp4][height<=1080]/best[ext=mp4]",
            "--output", str(temp / "video.%(ext)s"),
        ]
        last_error = ""
        # O UA alternativo é um workaround sugerido pelos mantenedores
        # do yt-dlp para os desafios intermitentes do TikTok.
        for attempt, extra in enumerate(([], ["--user-agent", "TikSalva/1.1"]), start=1):
            result = subprocess.run(
                common + extra + [clean_url],
                capture_output=True, text=True, timeout=PROCESS_TIMEOUT,
            )
            videos = [p for p in temp.glob("video.mp4") if p.is_file()]
            if result.returncode == 0 and videos:
                break
            last_error = result.stderr or result.stdout or ""
            # Mensagem diagnóstica limitada; sem publicar o link do usuário.
            short_error = re.sub(r"https?://\S+", "[url]", last_error)[-350:]
            logger.warning("TikTok extractor attempt=%s code=%s id=%s msg=%s",
                           attempt, result.returncode, video_id, short_error)
            if classify_error(last_error)[0] == 413:
                raise HTTPException(status_code=413, detail="O video ultrapassa 120 MB.")
        videos = [p for p in temp.glob("video.mp4") if p.is_file()]

        if not videos and payload.allow_external_fallback:
            logger.info("Attempting alternative source for public video id=%s", video_id)
            if alternative_download(clean_url, temp / "video.mp4"):
                videos = [temp / "video.mp4"]

        if not videos:
            status_code, reason = classify_error(last_error)
            if payload.allow_external_fallback:
                reason += " O metodo alternativo tambem nao conseguiu obter o arquivo."
            else:
                reason += " Marque o metodo alternativo se quiser tentar outro provedor."
            raise HTTPException(status_code=status_code, detail=reason)
        video = videos[0]
        if video.stat().st_size > MAX_BYTES:
            raise HTTPException(status_code=413, detail="O video ultrapassa 120 MB.")
        completed = True
        return FileResponse(
            path=video,
            media_type=mimetypes.guess_type(video.name)[0] or "video/mp4",
            filename=f"tiktok-{video_id}.mp4",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            background=BackgroundTask(shutil.rmtree, temp, ignore_errors=True),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="O TikTok demorou demais para responder. Tente novamente.") from exc
    finally:
        current.release()
        if not completed:
            shutil.rmtree(temp, ignore_errors=True)


@app.get("/")
def homepage():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def worker():
    return FileResponse(STATIC / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
