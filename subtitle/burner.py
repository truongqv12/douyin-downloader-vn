from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .ffmpeg import escape_filter_path, find_ffmpeg, run_ffmpeg


def build_subtitle_filter(ass_path: Path, fonts_dir: str = "") -> str:
    subtitle_filter = f"subtitles='{escape_filter_path(ass_path)}'"
    if fonts_dir:
        subtitle_filter += f":fontsdir='{escape_filter_path(Path(fonts_dir))}'"
    return subtitle_filter


def build_burn_command(
    *,
    video_path: Path,
    ass_path: Path,
    output_path: Path,
    ffmpeg_path: str = "",
    fonts_dir: str = "",
    video_codec: str = "libx264",
    audio_codec: str = "copy",
    crf: int = 18,
    preset: str = "medium",
    video_filter: str = "",
) -> List[str]:
    ffmpeg = find_ffmpeg(ffmpeg_path)
    filter_value = video_filter or build_subtitle_filter(ass_path, fonts_dir=fonts_dir)
    return [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        filter_value,
        "-c:v",
        video_codec,
        "-crf",
        str(crf),
        "-preset",
        preset,
        "-c:a",
        audio_codec,
        str(output_path),
    ]


def burn_ass(
    *,
    video_path: Path,
    ass_path: Path,
    output_path: Path,
    ffmpeg_path: str = "",
    fonts_dir: str = "",
    video_codec: str = "libx264",
    audio_codec: str = "copy",
    crf: int = 18,
    preset: str = "medium",
    video_filter: str = "",
    timeout: Optional[int] = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_burn_command(
        video_path=video_path,
        ass_path=ass_path,
        output_path=output_path,
        ffmpeg_path=ffmpeg_path,
        fonts_dir=fonts_dir,
        video_codec=video_codec,
        audio_codec=audio_codec,
        crf=crf,
        preset=preset,
        video_filter=video_filter,
    )
    run_ffmpeg(command, timeout=timeout)
