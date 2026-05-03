from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .models import SubtitleCue
from .srt_parser import parse_srt
from .style import AssStyle


def convert_srt_to_ass(input_path: Path, output_path: Path, style: AssStyle) -> None:
    cues = parse_srt(input_path)
    write_ass(output_path, cues, style)


def write_ass(path: Path, cues: Sequence[SubtitleCue], style: AssStyle) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(format_ass(cues, style), encoding="utf-8")


def format_ass(cues: Sequence[SubtitleCue], style: AssStyle) -> str:
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "Collisions: Normal",
        f"WrapStyle: {style.wrap_style}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: {style.to_ass_style_line()}",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for cue in cues:
        lines.append(
            "Dialogue: 0,"
            f"{_format_ass_time(cue.start_ms)},"
            f"{_format_ass_time(cue.end_ms)},"
            f"{style.name},,0,0,0,,{escape_ass_text(cue.text)}"
        )
    return "\n".join(lines).rstrip() + "\n"


def escape_ass_text(text: str) -> str:
    value = str(text or "")
    # Dấu ngoặc nhọn trong ASS là override tag; escape để text không đổi style ngoài ý muốn.
    value = value.replace("\\", "\\\\")
    value = value.replace("{", "\\{").replace("}", "\\}")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return value.replace("\n", "\\N")


def _format_ass_time(milliseconds: int) -> str:
    total_cs = max(0, int(round(int(milliseconds) / 10.0)))
    hours, remainder = divmod(total_cs, 3600 * 100)
    minutes, remainder = divmod(remainder, 60 * 100)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
