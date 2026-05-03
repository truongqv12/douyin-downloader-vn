from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .errors import FFmpegError


def find_ffmpeg(explicit_path: str = "") -> str:
    if explicit_path:
        return explicit_path
    found = shutil.which("ffmpeg")
    if found:
        return found
    local = Path(__file__).resolve().parent / "ffmpeg.exe"
    if local.exists():
        return str(local)
    raise FFmpegError("ffmpeg not found. Install ffmpeg or pass --ffmpeg-path")


def find_ffprobe(explicit_path: str = "", ffmpeg_path: str = "") -> str:
    if explicit_path:
        return explicit_path
    found = shutil.which("ffprobe")
    if found:
        return found
    if ffmpeg_path:
        ffmpeg = Path(ffmpeg_path)
        candidate = ffmpeg.with_name(
            "ffprobe.exe" if ffmpeg.name.lower().endswith(".exe") else "ffprobe"
        )
        if candidate.exists():
            return str(candidate)
    raise FFmpegError("ffprobe not found. Install ffmpeg/ffprobe or pass --ffprobe-path")


def escape_filter_path(path: Path) -> str:
    value = str(path)
    value = value.replace("\\", "\\\\")
    value = value.replace(":", "\\:")
    value = value.replace("'", "\\'")
    return value


def run_ffmpeg(command: List[str], timeout: Optional[int] = None) -> None:
    # Không dùng shell string để tránh lỗi path có dấu cách/Unicode và giảm rủi ro injection.
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffmpeg failed")


def probe_video_size(video_path: Path, ffprobe_path: str = "") -> Dict[str, int]:
    ffprobe = find_ffprobe(ffprobe_path)
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    if not streams:
        raise FFmpegError(f"no video stream found: {video_path}")
    stream = streams[0]
    return {"width": int(stream["width"]), "height": int(stream["height"])}
