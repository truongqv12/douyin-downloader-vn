from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence

from .errors import SubtitleParseError
from .models import SubtitleCue

_TIME_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})(?:\s+.*)?$"
)


def parse_srt(path: Path) -> List[SubtitleCue]:
    # utf-8-sig accepts normal UTF-8 and strips BOM from files exported by Windows tools.
    raw = Path(path).read_text(encoding="utf-8-sig")
    return parse_srt_text(raw)


def parse_srt_text(raw: str) -> List[SubtitleCue]:
    normalized = str(raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    cues: List[SubtitleCue] = []
    for block in re.split(r"\n{2,}", normalized):
        lines = block.split("\n")
        if len(lines) < 3:
            raise SubtitleParseError(f"invalid SRT block: {block!r}")

        try:
            index = int(lines[0].strip())
        except ValueError:
            raise SubtitleParseError(f"invalid SRT cue index: {lines[0]!r}")

        match = _TIME_RE.match(lines[1].strip())
        if not match:
            raise SubtitleParseError(f"invalid SRT timestamp: {lines[1]!r}")

        start_ms = parse_srt_time(match.group("start"))
        end_ms = parse_srt_time(match.group("end"))
        if end_ms <= start_ms:
            raise SubtitleParseError(f"cue {index} end time must be after start time")

        cues.append(
            SubtitleCue(
                index=index,
                start_ms=start_ms,
                end_ms=end_ms,
                text="\n".join(lines[2:]).strip(),
            )
        )
    return cues


def write_srt(path: Path, cues: Sequence[SubtitleCue]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(format_srt(cues), encoding="utf-8")


def format_srt(cues: Sequence[SubtitleCue]) -> str:
    blocks = []
    for cue in cues:
        blocks.append(
            "\n".join(
                [
                    str(cue.index),
                    f"{format_srt_time(cue.start_ms)} --> {format_srt_time(cue.end_ms)}",
                    str(cue.text or "").strip(),
                ]
            ).rstrip()
        )
    return "\n\n".join(blocks).rstrip() + "\n"


def parse_srt_time(value: str) -> int:
    try:
        hh, mm, rest = value.split(":")
        ss, ms = rest.split(",")
        return (
            int(hh) * 3600 * 1000
            + int(mm) * 60 * 1000
            + int(ss) * 1000
            + int(ms)
        )
    except Exception:
        raise SubtitleParseError(f"invalid SRT time: {value!r}")


def format_srt_time(milliseconds: int) -> str:
    total_ms = max(0, int(milliseconds))
    hours, remainder = divmod(total_ms, 3600 * 1000)
    minutes, remainder = divmod(remainder, 60 * 1000)
    seconds, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def validate_same_timing(
    original: Sequence[SubtitleCue], translated: Sequence[SubtitleCue]
) -> None:
    if len(original) != len(translated):
        raise SubtitleParseError(
            f"cue count changed after translation: {len(original)} != {len(translated)}"
        )
    for before, after in zip(original, translated):
        if (
            before.index != after.index
            or before.start_ms != after.start_ms
            or before.end_ms != after.end_ms
        ):
            raise SubtitleParseError(f"cue timing changed after translation: {before.index}")


def clone_with_texts(cues: Sequence[SubtitleCue], texts: Iterable[str]) -> List[SubtitleCue]:
    translated = [cue.with_text(text) for cue, text in zip(cues, texts)]
    validate_same_timing(cues, translated)
    return translated
