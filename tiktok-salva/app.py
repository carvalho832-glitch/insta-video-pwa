"""TikSalva - PWA para salvar videos publicos do TikTok autorizados pelo autor."""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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


@app.get("/api/health")
def health():
    return {"ok": True, "app": "TikSalva", "max_mb": MAX_MB}


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
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-playlist", "--no-progress", "--no-warnings",
            "--no-part", "--no-mtime", "--no-cache-dir",
            "--no-write-subs", "--no-write-auto-subs",
            "--no-write-thumbnail", "--no-write-info-json",
            "--no-write-description",
            "--max-filesize", f"{MAX_MB}M",
            "--socket-timeout", "15", "--retries", "1",
            "--fragment-retries", "1",
            "--format", "best[ext=mp4][height<=1080]/best[ext=mp4]",
            "--output", str(temp / "video.%(ext)s"),
            clean_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=PROCESS_TIMEOUT)
        if result.returncode:
            details = (result.stderr or "").lower()
            logger.warning("TikTok extraction failed (id=%s exit=%s)", video_id, result.returncode)
            if "larger than" in details or "max-filesize" in details or "file is larger" in details:
                raise HTTPException(status_code=413, detail="O video ultrapassa 120 MB.")
            if "login" in details or "private" in details or "not available" in details:
                raise HTTPException(status_code=422, detail="Video privado, indisponivel ou exige login. Use um video publico.")
            if "429" in details or "403" in details or "blocked" in details:
                raise HTTPException(status_code=422, detail="TikTok bloqueou o acesso deste servidor. Tente mais tarde.")
            raise HTTPException(status_code=422, detail="Nao foi possivel obter o MP4. O TikTok pode ter mudado o acesso a esse video.")

        candidates = [p for p in temp.glob("video.mp4") if p.is_file()]
        if not candidates:
            raise HTTPException(status_code=422, detail="Nao foi encontrado um arquivo MP4 compativel.")
        video = candidates[0]
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
