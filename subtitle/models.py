from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .errors import SubtitleParseError


@dataclass(frozen=True)
class SubtitleCue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    def with_text(self, text: str) -> "SubtitleCue":
        return SubtitleCue(
            index=self.index,
            start_ms=self.start_ms,
            end_ms=self.end_ms,
            text=text,
        )


@dataclass(frozen=True)
class MaskRect:
    x: int
    y: int
    w: int
    h: int

    @classmethod
    def parse(cls, raw: str) -> "MaskRect":
        parts = [p.strip() for p in str(raw or "").split(",")]
        if len(parts) != 4:
            raise SubtitleParseError("mask rect must use format x,y,w,h")
        try:
            x, y, w, h = [int(p) for p in parts]
        except ValueError:
            raise SubtitleParseError("mask rect values must be integers")
        rect = cls(x=x, y=y, w=w, h=h)
        rect.validate_basic()
        return rect

    def validate_basic(self) -> None:
        if self.x < 0 or self.y < 0:
            raise SubtitleParseError("mask rect x/y must be >= 0")
        if self.w <= 0 or self.h <= 0:
            raise SubtitleParseError("mask rect width/height must be > 0")

    def validate_bounds(self, video_width: int, video_height: int) -> None:
        self.validate_basic()
        if self.x + self.w > video_width or self.y + self.h > video_height:
            raise SubtitleParseError(
                "mask rect is outside video bounds: "
                f"rect={self.x},{self.y},{self.w},{self.h}, "
                f"video={video_width}x{video_height}"
            )

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    def to_cli_value(self) -> str:
        return f"{self.x},{self.y},{self.w},{self.h}"
