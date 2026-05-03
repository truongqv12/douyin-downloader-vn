from __future__ import annotations

from pathlib import Path
from typing import Tuple

from .ffmpeg import probe_video_size


def get_video_size(video_path: Path, ffprobe_path: str = "") -> Tuple[int, int]:
    size = probe_video_size(video_path, ffprobe_path=ffprobe_path)
    return size["width"], size["height"]
