from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from .errors import DependencyUnavailableError, FFmpegError, SubtitleParseError
from .ffmpeg import find_ffmpeg
from .models import MaskRect


def extract_preview_frame(
    *,
    video_path: Path,
    output_path: Path,
    timestamp: str = "00:00:03",
    ffmpeg_path: str = "",
) -> Path:
    ffmpeg = find_ffmpeg(ffmpeg_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-ss",
            timestamp,
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "failed to extract preview frame")
    return output_path


def pick_mask_rect(
    *,
    video_path: Path,
    timestamp: str = "00:00:03",
    output_json: Optional[Path] = None,
    ffmpeg_path: str = "",
) -> MaskRect:
    try:
        import cv2
    except ImportError:
        raise DependencyUnavailableError(
            "opencv-python is not installed. Install it or use preview frame fallback."
        )

    preview = (output_json.parent if output_json else Path.cwd()) / "mask_preview.jpg"
    extract_preview_frame(
        video_path=video_path,
        output_path=preview,
        timestamp=timestamp,
        ffmpeg_path=ffmpeg_path,
    )
    image = cv2.imread(str(preview))
    if image is None:
        raise SubtitleParseError(f"failed to open preview frame: {preview}")
    x, y, w, h = cv2.selectROI("Select old subtitle area", image, showCrosshair=True)
    cv2.destroyAllWindows()
    rect = MaskRect(int(x), int(y), int(w), int(h))
    rect.validate_basic()
    if output_json:
        write_rect_json(output_json, video_path=video_path, timestamp=timestamp, rect=rect)
    return rect


def write_rect_json(
    output_path: Path,
    *,
    video_path: Path,
    timestamp: str,
    rect: MaskRect,
    default_mode: str = "blur",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "video_path": str(video_path),
        "timestamp": timestamp,
        "rect": rect.to_dict(),
        "cli_args": f"--mask-mode {default_mode} --mask-rect {rect.to_cli_value()}",
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
