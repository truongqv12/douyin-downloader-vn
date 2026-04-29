from __future__ import annotations

from pathlib import Path
from typing import Optional

from .burner import build_subtitle_filter
from .errors import SubtitleParseError
from .models import MaskRect


def build_masked_subtitle_filter(
    *,
    ass_path: Path,
    fonts_dir: str = "",
    mode: str = "none",
    rect: Optional[MaskRect] = None,
    box_color: str = "black@0.85",
    blur_strength: int = 12,
) -> str:
    subtitle_filter = build_subtitle_filter(ass_path, fonts_dir=fonts_dir)
    normalized = (mode or "none").strip().lower()
    if normalized == "none":
        return subtitle_filter
    if rect is None:
        raise SubtitleParseError("mask rect is required when mask mode is not none")
    if normalized == "box":
        return f"{build_box_filter(rect, box_color=box_color)},{subtitle_filter}"
    if normalized == "crop":
        return f"{build_crop_filter(rect)},{subtitle_filter}"
    if normalized == "blur":
        return f"{build_blur_filter(rect, blur_strength=blur_strength)},{subtitle_filter}"
    raise SubtitleParseError(f"unsupported mask mode: {mode}")


def build_box_filter(rect: MaskRect, *, box_color: str = "black@0.85") -> str:
    rect.validate_basic()
    return (
        f"drawbox=x={rect.x}:y={rect.y}:w={rect.w}:h={rect.h}:"
        f"color={box_color}:t=fill"
    )


def build_crop_filter(rect: MaskRect) -> str:
    rect.validate_basic()
    return f"crop=iw:ih-{rect.h}:0:0"


def build_blur_filter(rect: MaskRect, *, blur_strength: int = 12) -> str:
    rect.validate_basic()
    blur = max(1, int(blur_strength or 1))
    # Tách vùng phụ đề cũ, blur riêng rồi overlay lại để không làm mờ toàn video.
    return (
        f"split[base][crop];"
        f"[crop]crop={rect.w}:{rect.h}:{rect.x}:{rect.y},boxblur={blur}:1[blur];"
        f"[base][blur]overlay={rect.x}:{rect.y}"
    )


def scale_rect_from_display(
    rect: MaskRect,
    *,
    display_width: int,
    display_height: int,
    video_width: int,
    video_height: int,
) -> MaskRect:
    if display_width <= 0 or display_height <= 0:
        raise SubtitleParseError("display size must be positive")
    scaled = MaskRect(
        x=round(rect.x * video_width / display_width),
        y=round(rect.y * video_height / display_height),
        w=round(rect.w * video_width / display_width),
        h=round(rect.h * video_height / display_height),
    )
    scaled.validate_bounds(video_width, video_height)
    return scaled
