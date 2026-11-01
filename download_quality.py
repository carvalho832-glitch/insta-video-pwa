"""Source-quality format selection for public Reels and video downloads.

Only select source formats; ffmpeg remuxing does not upscale or re-encode pixels.
"""
import sys

QUALITY_FORMATS = {
    "max": "bv+ba/b",
    "1080": "bv[height<=1080]+ba/b[height<=1080]",
    "720": "bv[height<=720]+ba/b[height<=720]",
}

def build_command(link: str, output_template: str, quality: str, executable: str | None = None):
    if quality not in QUALITY_FORMATS:
        raise ValueError("Selecione uma qualidade de vídeo válida.")
    return [
        executable or sys.executable, "-m", "yt_dlp",
        "--no-playlist", "--no-progress", "--no-warnings", "--no-part",
        "--max-filesize", "250M", "--socket-timeout", "20",
        "--retries", "2", "--fragment-retries", "2",
        "--concurrent-fragments", "2",
        # Max resolution first, then favour MP4-compatible codecs at the SAME resolution.
        "--format-sort", "res,fps,codec:h264:m4a,ext:mp4:m4a",
        "--format", QUALITY_FORMATS[quality],
        "--merge-output-format", "mp4",
        "--remux-video", "mp4",
        "--output", output_template, link,
    ]
