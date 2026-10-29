"""ReelSalva: videos publicos do Instagram e Facebook, sem login ou bypass."""
from __future__ import annotations
import base64
import binascii
import hmac
import logging
import os
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
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
MAX_SIZE = 250 * 1024 * 1024
DOWNLOAD_TIMEOUT = 90
LINK_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{4,80}$")
app = FastAPI(title="ReelSalva", docs_url=None, redoc_url=None)
lock = threading.Lock()
active = threading.BoundedSemaphore(2)
hits = defaultdict(deque)
log = logging.getLogger("reelsalva")
ACCESS_CODE = os.environ.get("REELSALVA_ACCESS_CODE", "").strip()

@app.middleware("http")
async def restrict_personal_access(request: Request, call_next):
    # A public health endpoint lets Cloud Run check readiness.
    if request.url.path == "/api/health":
        return await call_next(request)

    # Never expose a Cloud Run instance if the access code was omitted.
    if os.environ.get("K_SERVICE") and not ACCESS_CODE:
        return Response(
            "ReelSalva requires REELSALVA_ACCESS_CODE on Cloud Run.",
            status_code=503,
            media_type="text/plain",
        )

    if ACCESS_CODE:
        encoded = request.headers.get("Authorization", "")
        try:
            scheme, value = encoded.split(" ", 1)
            decoded = (
                base64.b64decode(value, validate=True).decode("utf-8")
                if scheme.lower() == "basic" else ""
            )
        except (ValueError, UnicodeDecodeError, binascii.Error):
            decoded = ""

        if not hmac.compare_digest(decoded, "julio:" + ACCESS_CODE):
            return Response(
                "Acesso restrito ao proprietario do ReelSalva.",
                status_code=401,
                media_type="text/plain",
                headers={
                    "WWW-Authenticate": 'Basic realm="ReelSalva", charset="UTF-8"',
                    "Cache-Control": "no-store",
                },
            )

    return await call_next(request)


class VideoLink(BaseModel):
    url: str = Field(min_length=10, max_length=1500)

def clean_link(value: str):
    found = LINK_RE.search(value.strip())
    if not found:
        raise ValueError("Cole um link de vídeo do Instagram ou Facebook.")
    url = urlparse(found.group(0).rstrip(").,;!]"))
    host = (url.hostname or "").lower()
    if url.scheme != "https" or url.username or url.password or url.port is not None:
        raise ValueError("Use o link HTTPS de compartilhamento do Instagram ou Facebook.")

    parts = [p for p in url.path.split("/") if p]
    if host in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
        if len(parts) < 2 or parts[0].lower() not in {"reel", "p", "tv"} or not CODE_RE.fullmatch(parts[1]):
            raise ValueError("Este link não aponta para um Reel ou publicação válida.")
        return f"https://www.instagram.com/{parts[0].lower()}/{parts[1]}/", parts[1], "instagram"

    if host in {"facebook.com", "www.facebook.com", "m.facebook.com", "mbasic.facebook.com",
                "web.facebook.com", "fb.watch", "www.fb.watch"}:
        if host.endswith("fb.watch"):
            if len(parts) != 1 or not CODE_RE.fullmatch(parts[0]):
                raise ValueError("Link fb.watch inválido.")
            return f"https://fb.watch/{parts[0]}/", parts[0], "facebook"

        query = parse_qs(url.query)
        if len(parts) == 3 and parts[0].lower() == "share" and parts[1].lower() in {"v", "r"} and CODE_RE.fullmatch(parts[2]):
            return f"https://www.facebook.com/share/{parts[1].lower()}/{parts[2]}/", parts[2], "facebook"
        if len(parts) == 2 and parts[0].lower() in {"reel", "reels"} and CODE_RE.fullmatch(parts[1]):
            return f"https://www.facebook.com/reel/{parts[1]}/", parts[1], "facebook"
        if (parts == ["watch"] or parts == ["video.php"]) and query.get("v"):
            video_id = query["v"][0]
            if re.fullmatch(r"[0-9]{5,30}", video_id):
                return f"https://www.facebook.com/watch/?v={video_id}", video_id, "facebook"
        if len(parts) >= 2 and parts[-2].lower() == "videos" and CODE_RE.fullmatch(parts[-1]):
            return f"https://www.facebook.com/{'/'.join(parts)}/", parts[-1], "facebook"
        raise ValueError("Link do Facebook não reconhecido. Use Compartilhar → Copiar link de um vídeo ou Reel público.")

    raise ValueError("Por enquanto, aceitamos apenas links do Instagram ou Facebook.")

def allow_request(ip: str):
    now = time.monotonic()
    with lock:
        q = hits[ip]
        while q and now - q[0] > 900:
            q.popleft()
        if len(q) >= 8:
            return False
        q.append(now)
        if len(hits) > 3000:
            for key, value in list(hits.items())[:1000]:
                if not value or now - value[-1] > 900:
                    hits.pop(key, None)
        return True

@app.get("/api/health")
def health():
    return {"ok": True, "service": "ReelSalva"}

@app.post("/api/download")
def download(body: VideoLink, request: Request):
    try:
        link, code, platform = clean_link(body.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    ip = request.client.host if request.client else "unknown"
    if not allow_request(ip):
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.")
    if not active.acquire(blocking=False):
        raise HTTPException(503, "Servico ocupado. Tente novamente em instantes.")
    directory = Path(tempfile.mkdtemp(prefix="reelsalva-"))
    try:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-playlist", "--no-progress", "--no-warnings", "--no-part",
            "--max-filesize", "250M", "--socket-timeout", "15",
            "--retries", "1", "--fragment-retries", "1",
            "--format", "best[ext=mp4][height<=720]/best[ext=mp4]/best",
            "--output", str(directory / "video.%(ext)s"), link
        ]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT, check=False)
        if done.returncode != 0:
            error = (done.stderr or "").lower()
            if "larger than max-filesize" in error or "file is larger than" in error:
                log.warning("%s extractor: file exceeds configured size limit, video=%s", platform, code)
                raise HTTPException(413, "Este video supera o limite de 250 MB.")
            service = "Facebook" if platform == "facebook" else "Instagram"
            if "429" in error or "too many requests" in error:
                reason = "rate_limit"
                message = f"O {service} limitou temporariamente o acesso. Tente novamente mais tarde."
            elif any(word in error for word in ("login", "private", "authentication", "cookies", "not available", "not accessible")):
                reason = "login_or_private"
                message = f"Este vídeo do {service} pode ser privado ou exigir login. Só baixamos vídeos públicos."
            else:
                reason = "video_unavailable"
                message = f"O {service} não liberou este vídeo para o servidor. Confira se o vídeo é público e tente novamente."
            log.warning("%s extractor failed (reason=%s, code=%s, video=%s)", platform, reason, done.returncode, code)
            raise HTTPException(422, message)
        videos = [p for p in directory.glob("video.*") if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".webm"}]
        if not videos:
            raise HTTPException(422, "Não foi possível obter um arquivo de vídeo.")
        video = max(videos, key=lambda p: p.stat().st_size)
        if video.stat().st_size > MAX_SIZE:
            raise HTTPException(413, "O video supera o limite de 250 MB.")
        return FileResponse(
            video, filename=f"{platform}-{code}{video.suffix.lower()}",
            media_type=mimetypes.guess_type(video.name)[0] or "video/mp4",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True))
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "O site demorou demais para responder. Tente novamente.") from exc
    finally:
        active.release()
        if sys.exc_info()[0] is not None:
            shutil.rmtree(directory, ignore_errors=True)

@app.get("/")
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/sw.js")
def sw():
    return FileResponse(WEB / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

app.mount("/assets", StaticFiles(directory=WEB), name="assets")
