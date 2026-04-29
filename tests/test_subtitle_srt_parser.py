import pytest

from subtitle.errors import SubtitleParseError
from subtitle.srt_parser import (
    format_srt,
    format_srt_time,
    parse_srt,
    parse_srt_text,
    parse_srt_time,
    validate_same_timing,
)


def test_parse_srt_handles_bom_crlf_and_multiline(tmp_path):
    path = tmp_path / "input.srt"
    path.write_text(
        "\ufeff1\r\n00:00:01,000 --> 00:00:02,500\r\n你好\r\n世界\r\n\r\n"
        "2\r\n00:00:03,000 --> 00:00:04,000\r\n再见\r\n",
        encoding="utf-8",
    )

    cues = parse_srt(path)

    assert len(cues) == 2
    assert cues[0].index == 1
    assert cues[0].start_ms == 1000
    assert cues[0].end_ms == 2500
    assert cues[0].text == "你好\n世界"


def test_format_srt_round_trip():
    cues = parse_srt_text(
        "1\n00:00:01,000 --> 00:00:02,000\nXin chào\n\n"
        "2\n00:00:03,250 --> 00:00:04,500\nTạm biệt\n"
    )
    rendered = format_srt(cues)

    assert rendered.endswith("\n")
    assert parse_srt_text(rendered) == cues


def test_parse_srt_rejects_invalid_time_order():
    with pytest.raises(SubtitleParseError):
        parse_srt_text("1\n00:00:02,000 --> 00:00:01,000\nbad\n")


def test_srt_time_helpers():
    assert parse_srt_time("01:02:03,456") == 3723456
    assert format_srt_time(3723456) == "01:02:03,456"


def test_validate_same_timing_rejects_changed_timestamp():
    cues = parse_srt_text("1\n00:00:01,000 --> 00:00:02,000\nA\n")
    changed = [cues[0].with_text("B")]
    validate_same_timing(cues, changed)

    changed_time = [type(cues[0])(1, 1001, 2000, "B")]
    with pytest.raises(SubtitleParseError):
        validate_same_timing(cues, changed_time)
